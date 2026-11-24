import { chromium } from 'playwright';
import { preview } from 'vite';
import { mkdir } from 'node:fs/promises';

const widths = [320, 360, 390, 430, 768, 1024, 1366];
const output = 'artifacts';
await mkdir(output, { recursive: true });

const externalUrl = process.env.ACADEMY_TEST_URL;
const server = externalUrl ? null : await preview({
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
});
const baseUrl = externalUrl || 'http://127.0.0.1:4173/';
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.ACADEMY_CHROMIUM,
  args: ['--no-sandbox'],
});
const failures = [];

try {
  for (const width of widths) {
    const page = await browser.newPage({
      viewport: { width, height: 900 },
      deviceScaleFactor: 1,
      reducedMotion: 'reduce',
    });
    page.on('pageerror', error => {
      const message = width + 'px JavaScript error at ' + page.url() + ': ' + error.message;
      failures.push(message);
      console.error(message);
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.academy-header');
    await page.waitForTimeout(180);

    const initial = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
    }));
    if (initial.innerWidth !== width) failures.push(width + 'px viewport mismatch: ' + initial.innerWidth);
    if (initial.documentWidth > width + 1 || initial.bodyWidth > width + 1) {
      failures.push(width + 'px home horizontal overflow: document=' + initial.documentWidth + ', body=' + initial.bodyWidth);
    }
    if (width <= 720 && !(await page.locator('.mobile-menu').isVisible())) failures.push(width + 'px mobile menu is not visible');
    if (width > 720 && !(await page.getByRole('button', { name: 'CODE STUDIO', exact: true }).isVisible())) failures.push(width + 'px desktop navigation is not visible');
    await page.screenshot({ path: output + '/home-' + width + '.png', fullPage: true });

    if (width <= 720) await page.locator('.mobile-menu').click();
    await page.getByRole('button', { name: 'SIGNAL JOURNEY', exact: true }).click();
    await page.waitForSelector('.stage-visual');
    if (await page.locator('.stage-rail button').count() !== 8) failures.push(width + 'px signal journey does not expose all eight stages');
    if (await page.locator('.trace-tabs button').count() !== 5) failures.push(width + 'px end-to-end trace does not expose all five implementation layers');
    await page.locator('.stage-rail button').nth(7).click();
    await page.waitForFunction(() => document.querySelector('.trace-copy h5')?.textContent === 'After reception, the user inspects the result');
    await page.locator('.trace-tabs button').nth(2).click();
    await page.waitForFunction(() => document.querySelector('.trace-copy h5')?.textContent === 'The completed file crosses RX USB serial');
    if (!(await page.locator('.trace-detail').innerText()).includes('RX_FILE_HEX')) failures.push(width + 'px USB serial layer does not explain the completed RX_FILE_HEX handoff');
    await page.locator('.trace-tabs button').nth(0).click();
    await page.waitForTimeout(380);
    const stageWidth = await page.locator('.journey-content').evaluate(el => el.getBoundingClientRect().width);
    if (stageWidth > width + 1) failures.push(width + 'px journey panel exceeds viewport: ' + stageWidth);
    const journeyScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (journeyScroll > width + 1) failures.push(width + 'px journey horizontal overflow: ' + journeyScroll);
    if ([360, 390, 768, 1366].includes(width)) await page.screenshot({ path: output + '/journey-' + width + '.png', fullPage: true });
    await page.locator('.open-code-stage').click();
    await page.waitForSelector('.source-map-section');
    if (!(await page.locator('.code-lesson-head h3').innerText()).includes('Receive and save the completed RX file')) failures.push(width + 'px journey stage did not open its matching RX application code lesson');

    await page.locator('.editor-line').nth(1).click();
    if (width <= 720) {
      await page.getByRole('button', { name: 'Choose a source lesson' }).click();
      const search = page.getByRole('textbox', { name: 'Find a source lesson' });
      await search.fill('Encode one byte');
      await page.locator('.file-group button').first().click();
      await page.locator('.inline-line-note').waitFor({ state: 'visible' });
    }
    const lineExplain = await page.locator(width <= 720 ? '.inline-line-note' : '.editor-explain p').innerText();
    if (!lineExplain.trim()) failures.push(width + 'px code line explanation is empty');
    const codeScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (codeScroll > width + 1) failures.push(width + 'px code studio horizontal overflow: ' + codeScroll);
    if ([360, 390, 768, 1366].includes(width)) await page.screenshot({ path: output + '/code-' + width + '.png', fullPage: true });

    if (width <= 720) await page.locator('.mobile-menu').click();
    await page.getByRole('button', { name: 'DEEP DIVE', exact: true }).click();
    await page.waitForURL(url => url.hash === '#deepdive');
    await page.waitForSelector('.deep-dive-section');
    const inventoryStats = await page.locator('.deep-dive-stats').innerText();
    if (!inventoryStats.includes('88') || !inventoryStats.includes('56') || !inventoryStats.includes('960')) failures.push(width + 'px Deep Dive inventory totals are incomplete');
    await page.locator('.deep-search input').fill('tx_app_state.py');
    await page.locator('.deep-file-list button[data-path="application-source/gui_dev_v3/tx_app_state.py"]').click();
    if (!(await page.locator('.deep-file-head code').innerText()).endsWith('tx_app_state.py')) failures.push(width + 'px Deep Dive search did not select the TXAppState source file');
    if (!(await page.locator('.deep-symbol-list').innerText()).includes('start_transmission')) failures.push(width + 'px Deep Dive did not index TXAppState.start_transmission');
    await page.locator('.deep-symbol-list button').filter({ hasText: 'start_transmission' }).click();
    if (!(await page.locator('.deep-symbol-detail h4').innerText()).includes('start_transmission')) failures.push(width + 'px selecting a symbol did not open its function outline');
    if (!(await page.locator('.deep-symbol-detail > pre').innerText()).includes('def start_transmission')) failures.push(width + 'px function outline does not show its source signature');
    if (!(await page.locator('.deep-symbol-detail a').getAttribute('href')).includes('#L225-L')) failures.push(width + 'px function source span does not link to its indexed line range');
    await page.waitForFunction(
      () => document.querySelector('.deep-source-head')?.innerText.includes('LINES LOADED'),
      undefined,
      { timeout: 12000 },
    );
    if (!(await page.locator('.deep-source-viewer pre').innerText()).includes('def start_transmission')) failures.push(width + 'px inline source viewer does not show the selected function body');
    if (!(await page.locator('.deep-file-head a').getAttribute('href')).includes('/blob/411f183a')) failures.push(width + 'px Deep Dive full-source link is not pinned to the audited commit');
    const deepScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (deepScroll > width + 1) failures.push(width + 'px Deep Dive horizontal overflow: ' + deepScroll);
    if ([360, 390, 768, 1366].includes(width)) await page.screenshot({ path: output + '/deepdive-' + width + '.png', fullPage: true });

    if (width <= 720) await page.locator('.mobile-menu').click();
    await page.getByRole('button', { name: 'APP ATLAS', exact: true }).click();
    await page.waitForSelector('.app-atlas-section');
    await page.getByRole('tab', { name: 'RX APPLICATION' }).click();
    await page.getByRole('button', { name: /Inspect/ }).click();
    if (!(await page.locator('.atlas-detail-card h3').innerText()).includes('Inspect')) failures.push(width + 'px RX Inspect atlas entry did not open');
    await page.getByRole('tab', { name: 'SETTINGS' }).click();
    await page.getByRole('button', { name: 'RECEIVER' }).click();
    await page.getByRole('button', { name: /Invert Symbols/ }).click();
    if (!(await page.locator('.atlas-setting-detail').innerText()).includes('NOT HANDLED BY PINNED FIRMWARE')) failures.push(width + 'px unsupported RX setting was not flagged');
    await page.getByRole('tab', { name: 'SIGNAL & DATA' }).click();
    await page.getByRole('button', { name: /Table Builder preview/ }).click();
    if (!(await page.locator('.atlas-detail-card').last().innerText()).includes('MOCK / SYNTHETIC DATA')) failures.push(width + 'px Table Builder data provenance was not disclosed');
    const atlasScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (atlasScroll > width + 1) failures.push(width + 'px application atlas horizontal overflow: ' + atlasScroll);
    if ([360, 390, 768, 1366].includes(width)) await page.screenshot({ path: output + '/atlas-' + width + '.png', fullPage: true });

    if (width <= 720) await page.locator('.mobile-menu').click();
    await page.getByRole('button', { name: 'PRACTICE', exact: true }).click();
    await page.waitForSelector('.code-practice-lab');
    await page.locator('.practice-answer-options button').nth(1).click();
    await page.getByRole('button', { name: /CHECK ANSWER/ }).click();
    if (!(await page.locator('.practice-feedback').innerText()).includes('CORRECT')) failures.push(width + 'px code practice did not validate the correct TX selection answer');
    if (!(await page.locator('.practice-feedback-actions').innerText()).includes('OPEN CODE LESSON')) failures.push(width + 'px code practice did not offer its source lesson');
    const practiceScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (practiceScroll > width + 1) failures.push(width + 'px code practice horizontal overflow: ' + practiceScroll);
    if ([360, 390, 768, 1366].includes(width)) await page.screenshot({ path: output + '/practice-' + width + '.png', fullPage: true });

    if (width <= 720) await page.locator('.mobile-menu').click();
    await page.getByRole('button', { name: 'LEARNING PATHS', exact: true }).click();
    await page.locator('.path-card').first().click();
    await page.waitForSelector('.focused-lesson');
    await page.getByRole('button', { name: /MARK LESSON COMPLETE/ }).click();
    const progress = await page.locator('.path-detail-hero').innerText();
    if (!progress.includes('1 OF 4')) failures.push(width + 'px lesson progress did not update');
    const pathScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (pathScroll > width + 1) failures.push(width + 'px focused lesson horizontal overflow: ' + pathScroll);
    if ([360, 390, 768, 1366].includes(width)) await page.screenshot({ path: output + '/lesson-' + width + '.png', fullPage: true });

    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.focused-lesson');
    if (!(await page.locator('.path-detail-hero').innerText()).includes('1 OF 4')) failures.push(width + 'px lesson progress was not restored after reload');

    if (width <= 720) await page.locator('.mobile-menu').click();
    await page.getByRole('button', { name: 'TRANSFER LAB', exact: true }).click();
    await page.getByRole('heading', { name: 'File transfer lab' }).waitFor();
    await page.getByLabel('First-round condition').selectOption('corrupt');
    await page.getByRole('button', { name: 'Send rest of round' }).click();
    const downloadButton = page.getByRole('button', { name: 'Download received file' });
    if (!(await downloadButton.isDisabled())) failures.push(width + 'px lab enabled download with a corrupt frame');
    await page.getByRole('button', { name: 'Repeat full round' }).click();
    await page.getByRole('button', { name: 'Send rest of round' }).click();
    if (!(await downloadButton.isEnabled())) failures.push(width + 'px lab did not recover on the second round');
    const labScroll = await page.evaluate(() => document.documentElement.scrollWidth);
    if (labScroll > width + 1) failures.push(width + 'px transfer lab horizontal overflow: ' + labScroll);
    if ([390, 1366].includes(width)) {
      await page.screenshot({ path: output + '/lab-' + width + '.png', fullPage: true });
      const bytes = Buffer.from('OpenVLC browser round-trip test\n'.repeat(24));
      await page.locator('input[type=file]').setInputFiles({ name: 'fixture.txt', mimeType: 'text/plain', buffer: bytes });
      await page.getByText('fixture.txt', { exact: true }).waitFor();
      await page.getByLabel('First-round condition').selectOption('clean');
      await page.getByRole('button', { name: 'Send rest of round' }).click();
      const download = page.waitForEvent('download');
      await downloadButton.click();
      const emitted = await download;
      const stream = await emitted.createReadStream();
      const chunks = [];
      for await (const chunk of stream) chunks.push(chunk);
      if (!bytes.equals(Buffer.concat(chunks))) failures.push(width + 'px reconstructed download differed from the uploaded file');
    }

    if ([390, 1366].includes(width)) {
      await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
      await page.getByRole('button', { name: 'Send 0', exact: true }).click();
      await page.getByText('LED off · symbol 0', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Follow a file through light' }).click();
      await page.getByRole('heading', { name: 'How can an LED carry a byte?' }).waitFor();
      await page.getByLabel('Change the low nibble').selectOption('0');
      await page.getByText('0100 0000', { exact: true }).waitFor();
      if (await page.evaluate(() => document.documentElement.scrollWidth) > width + 1) failures.push(width + 'px Foundations horizontal overflow');
      await page.screenshot({ path: output + '/foundations-' + width + '.png', fullPage: true });
      await page.getByRole('button', { name: 'Next stage' }).click();
      await page.getByRole('slider', { name: 'Reference threshold' }).press('End');
      await page.getByText('0 · 0 · 0', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Next stage' }).click();
      await page.getByRole('button', { name: 'Send with one corrupt frame' }).click();
      await page.getByText('Rejected by CRC', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Repeat the full round' }).click();
      await page.getByText('Whole-file CRC passed.', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Try the guided transfer' }).click();
      await page.getByRole('complementary', { name: 'Guided transfer' }).waitFor();
      if (await page.getByLabel('First-round condition').inputValue() !== 'corrupt') failures.push(width + 'px guided Lab did not preload the corrupt frame exercise');
      await page.getByRole('button', { name: 'Open receiver validation code' }).click();
      await page.getByRole('heading', { name: 'Validate a complete frame' }).waitFor();
    }

    await page.close();
  }
} finally {
  await browser.close();
  if (server) await new Promise(resolve => server.httpServer.close(resolve));
}

if (failures.length) {
  console.error('Responsive visual smoke test failures:');
  for (const failure of failures) console.error('- ' + failure);
  process.exitCode = 1;
} else {
  console.log('Responsive visual smoke tests passed at ' + widths.join(', ') + ' CSS pixels.');
}
