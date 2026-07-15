const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const templateSource = fs.readFileSync(
  path.join(root, 'src/image_occlusion_enhanced/template.py'),
  'utf8',
);
const generatorSource = fs.readFileSync(
  path.join(root, 'src/image_occlusion_enhanced/ngen.py'),
  'utf8',
);

function tripleQuotedValue(name) {
  const match = templateSource.match(
    new RegExp(`${name} = """\\\\\\n([\\s\\S]*?)"""`),
  );
  assert(match, `Could not extract ${name}`);
  return match[1];
}

const css = tripleQuotedValue('iocard_css');
const stageScript = tripleQuotedValue('io_stage_script').replace(/\\\s*$/, '');

assert.match(
  css,
  /#io-revl-btn \{[\s\S]*margin: 18px auto var\(--content-padding\);/,
);

assert.match(generatorSource, /setAttribute\("viewBox"/);
assert.match(generatorSource, /setAttribute\("preserveAspectRatio", "none"\)/);

function imageDataUrl(width, height, body) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${body}</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

async function verifyLayout(page, width, height, wrappedFields = false) {
  const original = imageDataUrl(
    width,
    height,
    `<rect width="100%" height="100%" fill="white"/><rect x="10%" y="20%" width="30%" height="25%" fill="#ffe99f"/>`,
  );
  const overlay = imageDataUrl(
    width,
    height,
    `<rect x="10%" y="20%" width="30%" height="25%" fill="#ff6b78"/>`,
  );
  const originalField = wrappedFields
    ? `<div data-efdrcfield="Image"><img src="${original}"></div>`
    : `<img src="${original}">`;
  const overlayField = wrappedFields
    ? `<div data-efdrcfield="Mask"><img src="${overlay}"></div>`
    : `<img src="${overlay}">`;

  await page.setContent(`<!doctype html><html><head>
    <style>
      html, body { margin: 0; width: 100%; height: 100%; }
      img { width: 73%; height: 137px; max-height: 137px; transform: scaleX(.8); }
      ${css}
    </style></head><body class="card card-image-occlusion">
      <div class="title-header"><div class="content-frame"><div class="title-label">Centered title</div></div></div>
      <div class="front-wrapper"><div class="content-frame"><div class="question-content">Front text</div></div></div>
      <div id="io-wrapper"><div id="io-stage">
        <div id="io-original">${originalField}</div>
        <div id="io-overlay">${overlayField}</div>
      </div></div>
    ${stageScript}</body></html>`);
  await page.waitForFunction(() => document.querySelector('#io-stage').classList.contains('io-stage-ready'));

  const boxes = await page.evaluate(() => {
    const rect = (selector) => {
      const box = document.querySelector(selector).getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height, bottom: box.bottom };
    };
    return {
      stage: rect('#io-stage'),
      original: rect('#io-original img'),
      overlay: rect('#io-overlay img'),
      title: rect('.title-label'),
      content: rect('.content-frame'),
      viewport: { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight },
      documentHeight: document.documentElement.scrollHeight,
      colors: {
        card: getComputedStyle(document.querySelector('.card')).backgroundColor,
        header: getComputedStyle(document.querySelector('.title-header')).backgroundColor,
        title: getComputedStyle(document.querySelector('.title-label')).color,
      },
    };
  });

  for (const property of ['x', 'y', 'width', 'height']) {
    assert(Math.abs(boxes.original[property] - boxes.overlay[property]) < 0.5, `${property} differs`);
    assert(Math.abs(boxes.stage[property] - boxes.original[property]) < 0.5, `stage ${property} differs`);
  }
  assert(
    Math.abs(boxes.stage.width / boxes.stage.height - width / height) < 0.001,
    `aspect ratio changed: ${JSON.stringify(boxes.stage)} for ${width}x${height}`,
  );
  assert(boxes.stage.bottom <= boxes.viewport.height - 19, 'stage exceeds the available viewer height');
  assert.equal(
    boxes.documentHeight,
    boxes.viewport.height,
    `card creates an outer vertical scrollbar: ${JSON.stringify(boxes)}`,
  );
  assert(Math.abs(boxes.title.x + boxes.title.width / 2 - boxes.viewport.width / 2) < 0.5, 'title is not centered');
  assert(Math.abs(boxes.content.x + boxes.content.width / 2 - boxes.viewport.width / 2) < 0.5, 'content frame is not centered');
  assert(boxes.content.width < boxes.viewport.width, 'content frame is not constrained');
  assert.deepEqual(boxes.colors, {
    card: 'rgb(0, 0, 0)',
    header: 'rgb(23, 23, 22)',
    title: 'rgb(245, 206, 148)',
  });
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    await verifyLayout(page, 2000, 1000);
    await verifyLayout(page, 1000, 2000);
    await verifyLayout(page, 2000, 2000);
    await verifyLayout(page, 2000, 1000, true);
    await verifyLayout(page, 1000, 2000, true);
    await verifyLayout(page, 2000, 2000, true);
    console.log('card layout tests passed');
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
