from __future__ import annotations

from PIL import Image

from fileorganizer import duplicates


def test_flattened_image_data_prefers_pillow_121_api():
    class FakeImage:
        def __init__(self):
            self.used_flattened = False

        def get_flattened_data(self):
            self.used_flattened = True
            return (1, 2, 3)

        def getdata(self):
            raise AssertionError("legacy getdata fallback should not be used")

    image = FakeImage()

    assert duplicates._flattened_image_data(image) == [1, 2, 3]
    assert image.used_flattened is True


def test_flattened_image_data_falls_back_to_getdata():
    class LegacyImage:
        def getdata(self):
            return (4, 5, 6)

    assert duplicates._flattened_image_data(LegacyImage()) == [4, 5, 6]


def test_compute_phash_reads_real_image(tmp_path):
    image_path = tmp_path / "gradient.png"
    image = Image.new("L", (9, 8))
    for y in range(8):
        for x in range(9):
            image.putpixel((x, y), x * 20)
    image.save(image_path)

    phash = duplicates._compute_phash(str(image_path), hash_size=8)

    assert len(phash) == 64
    assert set(phash) <= {"0", "1"}
