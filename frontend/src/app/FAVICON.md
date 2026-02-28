# LawMate Favicon

## Implemented

- **icon.svg** – Main favicon (indigo square + white scale). Used by Next.js for browser tabs and the manifest.
- **manifest.ts** – PWA manifest with `theme_color` and `background_color` `#4F46E5`, and reference to `/icon.svg`.
- **apple-icon.svg** – Source asset for the Apple touch icon (same design, 180×180 export size).

## Optional (recommended for full support)

1. **apple-icon.png** (180×180)  
   Next.js only uses `.png`/`.jpg` for the Apple touch icon. Export a 180×180 PNG from `apple-icon.svg` (e.g. in Figma, Sketch, or an SVG→PNG tool) and save as **apple-icon.png** in this directory (`src/app/`). Then when users “Add to Home Screen” on iPhone, the icon will be used.

2. **favicon.ico** (32×32)  
   For older browsers, add **favicon.ico** in this directory. You can generate it from `icon.svg` using a converter (e.g. [realfavicongenerator.net](https://realfavicongenerator.net/) or `convert`/ImageMagick).

## Testing

- Use an incognito/private window to avoid cached favicons.
- On mobile, `theme_color` in the manifest will tint the browser UI (e.g. address bar) with LawMate indigo.
