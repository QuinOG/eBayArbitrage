import csv
import glob
import io
import os
import tempfile
import unittest
from unittest import mock

import collect_sold
from data import sold_parser

PRICE_FIELDS = ["part", "model", "value", "sales", "confidence", "kind"]
OLD_ROWS = [
    ["cpu", "Core i7-8700", "60.00", "10", "high", "exact"],
    ["gpu", "RTX 2060 6GB", "150.00", "9", "high", "exact"],
]
TITLE = "NVIDIA GeForce RTX 3060 12GB Graphics Card"
PAGE = "".join(f"Sold {d}\n{TITLE}\nPre-Owned\n$200.00\nFree delivery\n\n"
               for d in ["Nov 20, 2026", "Nov 18, 2026", "Nov 15, 2026"])


class BuildPricesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        for p in [mock.patch.object(sold_parser, "DATA_DIR", self.dir),
                  mock.patch.object(collect_sold, "RAW_DIR", os.path.join(self.dir, "raw")),
                  mock.patch("sys.stdout", new_callable=io.StringIO)]:
            p.start()
            self.addCleanup(p.stop)

    def write_csv(self, name, header, rows):
        with open(os.path.join(self.dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    def test_build_prices_keeps_unsaved_parts_and_cwd(self):
        self.write_csv("prices.csv", PRICE_FIELDS, OLD_ROWS)
        self.write_csv("cpu_price_table.csv", ["model", "value", "sales", "flag"],
                       [["Core i5-8500", "30.00", "12", ""]])  # stale, from an earlier run
        os.makedirs(os.path.join(self.dir, "raw", "gpu"))
        with open(os.path.join(self.dir, "raw", "gpu", "x.txt"), "w", encoding="utf-8") as f:
            f.write(PAGE)
        cwd = os.getcwd()

        collect_sold.build_prices(["cpu", "mobo", "ram", "gpu"])

        self.assertEqual(os.getcwd(), cwd)
        self.assertTrue(glob.glob(os.path.join(self.dir, "prices_backup_*.csv")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "cpu_price_table.csv")))
        with open(os.path.join(self.dir, "prices.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r for r in rows if r["part"] == "cpu"], [dict(zip(PRICE_FIELDS, OLD_ROWS[0]))])
        gpu = [r for r in rows if r["part"] == "gpu"]
        self.assertEqual([r["model"] for r in gpu], ["RTX 3060 12GB"])
        self.assertEqual(gpu[0]["value"], "200.0")


if __name__ == "__main__":
    unittest.main()
