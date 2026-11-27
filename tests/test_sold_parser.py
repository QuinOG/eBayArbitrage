import csv
import io
import os
import tempfile
import unittest
from unittest import mock

from data import sold_parser

PRICE_HEADER = ["model", "value", "sales", "flag"]
PRICE_FIELDS = ["part", "model", "value", "sales", "confidence", "kind"]
OLD_ROWS = [
    ["cpu", "Core i7-8700", "60.00", "10", "high", "exact"],
    ["mobo", "MSI B450 TOMAHAWK MAX", "80.00", "5", "high", "exact"],
    ["mobo", "B450", "75.00", "8", "high", "fallback"],
    ["ram", "DDR4 Desktop 16GB (2x8GB) 3200", "40.00", "6", "high", "exact"],
    ["gpu", "RTX 3060 12GB", "200.00", "9", "high", "exact"],
]


class CombineTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        patcher = mock.patch.object(sold_parser, "DATA_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        out = mock.patch("sys.stdout", new_callable=io.StringIO)
        out.start()
        self.addCleanup(out.stop)

    def path(self, name):
        return os.path.join(self.dir, name)

    def write_csv(self, name, header, rows):
        with open(self.path(name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    def write_old_prices(self, rows=OLD_ROWS):
        self.write_csv("prices.csv", PRICE_FIELDS, rows)

    def read_prices(self):
        with open(self.path("prices.csv"), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def rows_for(self, part, rows=None):
        return [r for r in (rows if rows is not None else self.read_prices()) if r["part"] == part]


class CombineKeepsUnrefreshedParts(CombineTestCase):
    def test_refreshing_cpu_keeps_other_parts(self):
        self.write_old_prices()
        self.write_csv("cpu_price_table.csv", PRICE_HEADER,
                       [["Core i5-8500", "30.00", "12", ""], ["Ryzen 5 3600", "70.00", "2", "low data"]])

        sold_parser.combine()

        rows = self.read_prices()
        self.assertEqual(self.rows_for("cpu", rows), [
            dict(zip(PRICE_FIELDS, ["cpu", "Core i5-8500", "30.00", "12", "high", "exact"])),
            dict(zip(PRICE_FIELDS, ["cpu", "Ryzen 5 3600", "70.00", "2", "low", "exact"])),
        ])
        for part in ["mobo", "ram", "gpu"]:
            self.assertEqual(self.rows_for(part, rows),
                             [dict(zip(PRICE_FIELDS, r)) for r in OLD_ROWS if r[0] == part])

    def test_refreshing_mobo_keeps_old_fallback_rows_when_no_chipset_table(self):
        self.write_old_prices()
        self.write_csv("mobo_price_table.csv", PRICE_HEADER, [["ASUS TUF B550-PLUS", "110.00", "4", ""]])

        sold_parser.combine()

        mobo = self.rows_for("mobo")
        self.assertEqual(mobo, [
            dict(zip(PRICE_FIELDS, ["mobo", "ASUS TUF B550-PLUS", "110.00", "4", "high", "exact"])),
            dict(zip(PRICE_FIELDS, ["mobo", "B450", "75.00", "8", "high", "fallback"])),
        ])
        self.assertNotIn("MSI B450 TOMAHAWK MAX", [r["model"] for r in mobo])


class CombineWritesSafely(CombineTestCase):
    def test_no_tables_exits_and_leaves_prices_unchanged(self):
        self.write_old_prices()
        with open(self.path("prices.csv"), "rb") as f:
            before = f.read()

        with self.assertRaises(SystemExit):
            sold_parser.combine()

        with open(self.path("prices.csv"), "rb") as f:
            self.assertEqual(f.read(), before)

    def test_creates_prices_csv_from_all_four_tables(self):
        self.write_csv("cpu_price_table.csv", PRICE_HEADER, [["Core i5-8500", "30.00", "12", ""]])
        self.write_csv("mobo_price_table.csv", PRICE_HEADER, [["ASUS TUF B550-PLUS", "110.00", "4", ""]])
        self.write_csv("mobo_chipset_table.csv", ["chipset", "value", "sales"], [["B550", "100.00", "4"]])
        self.write_csv("ram_price_table.csv", PRICE_HEADER, [["DDR4 Desktop 16GB (2x8GB) 3200", "40.00", "6", ""]])
        self.write_csv("ram_capacity_table.csv", ["type_and_total", "value", "sales"],
                       [["DDR4 Desktop 16GB", "41.00", "6"]])
        self.write_csv("gpu_price_table.csv", PRICE_HEADER, [["RTX 3060 12GB", "200.00", "9", ""]])

        sold_parser.combine()

        rows = self.read_prices()
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["part"] for r in rows}, {"cpu", "mobo", "ram", "gpu"})
        self.assertEqual({(r["part"], r["kind"]) for r in rows},
                         {("cpu", "exact"), ("mobo", "exact"), ("mobo", "fallback"),
                          ("ram", "exact"), ("ram", "fallback"), ("gpu", "exact")})

    def test_confidence_from_flag_and_fallback_sales(self):
        self.write_csv("cpu_price_table.csv", PRICE_HEADER,
                       [["Core i5-8500", "30.00", "12", ""], ["Ryzen 5 3600", "70.00", "2", "low data"]])
        self.write_csv("mobo_price_table.csv", PRICE_HEADER, [["ASUS TUF B550-PLUS", "110.00", "4", ""]])
        self.write_csv("mobo_chipset_table.csv", ["chipset", "value", "sales"],
                       [["B550", "100.00", "2"], ["X570", "150.00", "3"]])

        sold_parser.combine()

        confidence = {(r["model"], r["kind"]): r["confidence"] for r in self.read_prices()}
        self.assertEqual(confidence[("Ryzen 5 3600", "exact")], "low")
        self.assertEqual(confidence[("Core i5-8500", "exact")], "high")
        self.assertEqual(confidence[("B550", "fallback")], "low")
        self.assertEqual(confidence[("X570", "fallback")], "high")

    def test_no_temp_file_left_after_success(self):
        self.write_old_prices()
        self.write_csv("cpu_price_table.csv", PRICE_HEADER, [["Core i5-8500", "30.00", "12", ""]])

        sold_parser.combine()

        self.assertTrue(os.path.exists(self.path("prices.csv")))
        self.assertFalse(os.path.exists(self.path("prices.csv.tmp")))


if __name__ == "__main__":
    unittest.main()
