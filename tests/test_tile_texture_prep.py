"""Manufacturer tile packs become bounded deterministic render atlases without network in tests."""
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image

from scripts.prepare_tile_texture import archive_images, build_atlas, page_asset_urls, select_images


def image_bytes(size, value):
    stream = io.BytesIO()
    Image.new('RGB', size, (value, value, value)).save(stream, format='JPEG')
    return stream.getvalue()


class TileTexturePrepTests(unittest.TestCase):
    def test_product_page_assets_include_texture_archives_and_tile_images(self):
        page = '''
        <a href="/downloads/calacatta-gold-textures.zip">Tekstury</a>
        <img src="https://cdn.example.test/calacatta-gold-60x120-01.jpg"
             srcset="https://cdn.example.test/calacatta-gold-60x120-01-small.jpg 600w,
                     https://cdn.example.test/calacatta-gold-60x120-01-large.jpg 1600w">
        <meta property="og:image" content="/media/calacatta-gold-room.webp">
        '''
        assets = page_asset_urls('https://cerrad.example.test/product', page)
        self.assertIn('https://cerrad.example.test/downloads/calacatta-gold-textures.zip', assets)
        self.assertIn('https://cdn.example.test/calacatta-gold-60x120-01.jpg', assets)
        self.assertIn('https://cdn.example.test/calacatta-gold-60x120-01-large.jpg', assets)
        self.assertIn('https://cerrad.example.test/media/calacatta-gold-room.webp', assets)

    def test_nested_texture_zip_is_filtered_and_built_as_4x4_atlas(self):
        nested_stream = io.BytesIO()
        with zipfile.ZipFile(nested_stream, 'w') as nested:
            nested.writestr('calacatta_gold_matt_598x1198_01.jpg', image_bytes((598, 1198), 80))
            nested.writestr('calacatta_gold_matt_598x1198_02.jpg', image_bytes((598, 1198), 120))
            nested.writestr('calacatta_gold_598x598.jpg', image_bytes((598, 598), 160))
        outer_stream = io.BytesIO()
        with zipfile.ZipFile(outer_stream, 'w') as outer:
            outer.writestr('textures.zip', nested_stream.getvalue())
            outer.writestr('preview.jpg', image_bytes((400, 300), 200))
        images = archive_images(outer_stream.getvalue())
        selected = select_images(images, ['gold', 'matt', '598', '1198'])
        self.assertEqual(len(selected), 2)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'atlas.jpg'
            names = build_atlas(selected, output, 4, 4, [128, 64])
            self.assertEqual(len(names), 16)
            with Image.open(output) as atlas:
                self.assertEqual(atlas.size, (512, 256))


if __name__ == '__main__':
    unittest.main()
