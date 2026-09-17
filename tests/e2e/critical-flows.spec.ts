import { expect, test, type Locator, type Page } from '@playwright/test'

async function openMapTools(page: Page): Promise<void> {
  const tools = page.locator('.compact-panel').filter({ hasText: 'Tools' })
  const toggle = tools.locator('.p-panel-toggle-button')
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
    await toggle.click()
  }
}

async function expectVerticalScroll(locator: Locator): Promise<void> {
  await expect(locator).toBeVisible()
  const result = await locator.evaluate((element) => {
    const target = element as HTMLElement
    const before = target.scrollTop
    target.scrollTop = Math.min(80, target.scrollHeight - target.clientHeight)
    const after = target.scrollTop
    target.scrollTop = before
    return {
      after,
      before,
      clientHeight: target.clientHeight,
      overflowY: getComputedStyle(target).overflowY,
      scrollHeight: target.scrollHeight,
    }
  })
  expect(result.scrollHeight).toBeGreaterThan(result.clientHeight)
  expect(result.overflowY).toMatch(/auto|scroll/)
  expect(result.after).toBeGreaterThan(result.before)
}

test('navigates across all four tools', async ({ page }) => {
  await page.goto('/map')
  await expect(page.getByText('Palworld Checklist', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Interactive Palworld map')).toBeVisible()

  await page.getByRole('link', { name: 'Lists' }).click()
  await expect(page.getByRole('heading', { name: 'Progress lists' })).toBeVisible()

  await page.getByRole('link', { name: 'Cakes' }).click()
  await expect(page.getByRole('heading', { name: 'Cake calculator' })).toBeVisible()

  await page.getByRole('link', { name: 'Breeding' }).click()
  await expect(page.getByRole('heading', { name: 'Breeding tools' })).toBeVisible()
})

test('centers typed coordinates and keeps the dark theme', async ({ page }) => {
  await page.goto('/map')
  await openMapTools(page)
  const input = page.getByPlaceholder('-16, -339')
  await input.fill('-16, -339')
  await input.press('Enter')
  await expect(page.getByText('Centered on (-16, -339)')).toBeVisible()

  await expect(page.locator('.app-shell')).toHaveClass(/app-dark/)
  await page.reload()
  await expect(page.locator('.app-shell')).toHaveClass(/app-dark/)
})

test('reports an error when OCR is unavailable', async ({ page }) => {
  await page.route('**/health', async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        version: 'test',
        anchor: [0, 0],
        active: false,
        x: 0,
        y: 0,
        label: '',
      },
    })
  })
  await page.route('**/ocr-select', async (route) => {
    await route.fulfill({ status: 503, json: { ok: false, error: 'unavailable' } })
  })
  await page.goto('/map')
  await openMapTools(page)
  await page.getByLabel('Read coordinates from screen').click()
  await expect(page.getByText('OCR unavailable')).toBeVisible()
})

test('persists selected breeding Pals immediately', async ({ page }) => {
  await page.route('**/progress', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({
      json: {
        version: 2,
        revision: 0,
        updatedAt: '',
        checks: {
          alphas: {},
          bounties: {},
          effigies: {},
          dungeons: {},
          towers: {},
          journals: {},
          oilrigs: {},
          camps: {},
          collectibles: {},
          travel: {},
        },
        breedOwned: {},
        prefs: {},
      },
    })
  })
  await page.goto('/breeding')
  const firstPal = page.locator('.owned-grid .pal-chip').first()
  await firstPal.click()
  await expect(firstPal).toHaveClass(/owned/)

  const stored = await page.evaluate(() => {
    const dedicated = JSON.parse(localStorage.getItem('palworld-breed-owned-v1') ?? '{}') as Record<
      string,
      true
    >
    const progress = JSON.parse(localStorage.getItem('palworld-progress-v2') ?? '{}') as {
      breedOwned?: Record<string, true>
    }
    return { dedicated, progress: progress.breedOwned }
  })
  expect(stored.progress).toEqual(stored.dedicated)

  await page.reload()
  await expect(page.locator('.owned-grid .pal-chip').first()).toHaveClass(/owned/)
})

test('supports vertical scrolling across every application area', async ({ page }) => {
  await page.goto('/lists')
  await page
    .locator('.category-section')
    .filter({ hasText: 'Gathering' })
    .evaluate((element) => {
      const details = element as HTMLDetailsElement
      details.open = true
    })
  await expectVerticalScroll(page.locator('.sidebar-scroll'))
  await expectVerticalScroll(page.locator('.list-scroller'))

  await page.goto('/map')
  await page
    .locator('.category-section')
    .filter({ hasText: 'Gathering' })
    .evaluate((element) => {
      const details = element as HTMLDetailsElement
      details.open = true
    })
  await expectVerticalScroll(page.locator('.sidebar-scroll'))

  await page.goto('/cakes')
  await expectVerticalScroll(page.locator('.content-pane'))

  await page.goto('/breeding')
  await expectVerticalScroll(page.locator('.content-pane'))
})
