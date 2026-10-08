import os
import numpy as np
from PIL import Image

mask_img = Image.open('assets/masks/bathroom_entrance_zones_2000x1600.png').convert('RGB')
mask_arr = np.array(mask_img)

r, g, b = mask_arr[:,:,0] > 128, mask_arr[:,:,1] > 128, mask_arr[:,:,2] > 128

zones = {
    'podloga': r & (~g) & (~b),
    'sciana_lewa': (~r) & g & (~b),
    'sciana_srodkowa': (~r) & (~g) & b,
    'sciana_prawa': r & g & (~b),
    'sufit': (~r) & g & b,
}

sample_render = '/sdcard/Download/Dom_Lazienka_R07_Wszystkie/01_cersanit_ikarus_white_matt_entrance_dimmed50.png'
if not os.path.exists(sample_render):
    sample_render = '/sdcard/Download/Dom_Lazienka_R07_Wszystkie/01_cersanit_ikarus_white_matt_entrance.png'

img = Image.open(sample_render).convert('RGBA')
img_arr = np.array(img)

out_dir = '/tmp/test_puzzle_01'
os.makedirs(out_dir, exist_ok=True)

for name, zone_mask in zones.items():
    piece = img_arr.copy()
    # set alpha to 0 outside mask
    piece[~zone_mask, 3] = 0
    piece_img = Image.fromarray(piece, 'RGBA')
    piece_path = os.path.join(out_dir, f'01_{name}.png')
    piece_img.save(piece_path)
    print(f'Saved {name} -> {piece_path} (non-zero alpha px: {np.sum(zone_mask)})')

# Now test recombining 5 pieces back into a full image
combined = Image.new('RGBA', (2000, 1600), (0, 0, 0, 0))
for name in zones:
    piece_path = os.path.join(out_dir, f'01_{name}.png')
    p = Image.open(piece_path)
    combined.alpha_composite(p)

combined_rgb = combined.convert('RGB')
combined_rgb.save(os.path.join(out_dir, 'recombined.png'))

orig = Image.open(sample_render).convert('RGB')
diff = np.abs(np.array(orig).astype(int) - np.array(combined_rgb).astype(int))
print('Max pixel difference between original and recombined puzzle:', np.max(diff))
print('Mean pixel difference:', np.mean(diff))
