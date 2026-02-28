// scripts/package.js
// Creates a production-ready ZIP file for Chrome Web Store submission

const fs = require('fs');
const path = require('path');
const archiver = require('archiver');

const DIST_DIR = path.join(__dirname, '../dist');
const OUTPUT_FILE = path.join(__dirname, '../lawmate-extension.zip');

// Validate dist directory exists
if (!fs.existsSync(DIST_DIR)) {
  console.error('❌ Error: dist/ directory not found. Run "npm run build" first.');
  process.exit(1);
}

// Delete old ZIP if exists
if (fs.existsSync(OUTPUT_FILE)) {
  fs.unlinkSync(OUTPUT_FILE);
  console.log('🗑️  Deleted old ZIP file');
}

// Create output stream
const output = fs.createWriteStream(OUTPUT_FILE);
const archive = archiver('zip', {
  zlib: { level: 9 } // Maximum compression
});

// Handle stream events
output.on('close', () => {
  const sizeInMB = (archive.pointer() / 1024 / 1024).toFixed(2);
  console.log(`\n✅ Package created successfully!`);
  console.log(`📦 File: ${OUTPUT_FILE}`);
  console.log(`📊 Size: ${sizeInMB} MB`);
  console.log(`📄 Files: ${archive.pointer()} bytes`);
  
  if (archive.pointer() > 50 * 1024 * 1024) {
    console.warn('\n⚠️  Warning: ZIP exceeds 50MB Chrome Web Store limit!');
  } else {
    console.log('\n🚀 Ready for Chrome Web Store submission!');
  }
});

archive.on('error', err => {
  throw err;
});

archive.on('warning', err => {
  if (err.code === 'ENOENT') {
    console.warn('⚠️  Warning:', err.message);
  } else {
    throw err;
  }
});

// Pipe archive to output file
archive.pipe(output);

console.log('📦 Creating Chrome Web Store package...\n');

// Add all files from dist, excluding source maps
archive.glob('**/*', {
  cwd: DIST_DIR,
  ignore: ['**/*.map'] // Exclude source maps
});

// Finalize the archive
archive.finalize();