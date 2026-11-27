import unittest

import scanner
from data.sold_parser import extract_gpu, extract_ram


def ram(title):
    found = extract_ram(scanner.clean_title("ram", title))
    return found[1] if found else None


class GPUExtractorTests(unittest.TestCase):
    def test_gpu_memory_after_16gb_system_ram(self):
        title = "Gaming PC Ryzen 5 5600X 16GB DDR4 RTX 3060 12GB"
        self.assertEqual(extract_gpu(title)[1], "RTX 3060 12GB")

    def test_gpu_memory_after_8gb_system_ram(self):
        title = "Gaming PC i5-9600K 8GB DDR4 RTX 3060 12GB"
        self.assertEqual(extract_gpu(title)[1], "RTX 3060 12GB")

    def test_gpu_memory_after_card_variant(self):
        title = "MSI RTX 3060 Ventus 2X 12G OC"
        self.assertEqual(extract_gpu(title)[1], "RTX 3060 12GB")

    def test_gpu_memory_before_model(self):
        title = "12GB RTX 3060 Gaming OC"
        self.assertEqual(extract_gpu(title)[1], "RTX 3060 12GB")

    def test_missing_gpu_memory(self):
        title = "RTX 3060 graphics card"
        self.assertEqual(extract_gpu(title)[1], "RTX 3060 (VRAM unknown)")

    def test_system_ram_without_gpu_memory(self):
        title = "Gaming PC 16GB RAM RTX 3060"
        self.assertEqual(extract_gpu(title)[1], "RTX 3060 (VRAM unknown)")


class RAMExtractorTests(unittest.TestCase):
    def test_ram_after_cpu_model_ending_in_x(self):
        title = "Gaming PC Ryzen 5 5600X 16GB DDR4 RTX 3060 12GB"
        self.assertEqual(ram(title), "DDR4 Desktop 16GB (1x16GB)")

    def test_ram_kit_in_parentheses(self):
        title = "Corsair Vengeance 16GB (2x8GB) DDR4 3200"
        self.assertEqual(ram(title), "DDR4 Desktop 16GB (2x8GB) 3200")

    def test_ram_kit_without_parentheses(self):
        title = "Kingston 2x8GB DDR4 2666"
        self.assertEqual(ram(title), "DDR4 Desktop 16GB (2x8GB) 2666")
