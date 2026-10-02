import { expect, test } from '@playwright/test'

test('shows Pal and human locations and keeps map filters synchronized across zones', async ({
  page,
}) => {
  await page.goto('/map')

  const mapLocations = page.locator('.map-locations-group')
  await expect(mapLocations.getByRole('tab', { name: 'Pal Locations' })).toBeVisible()
  const palOption = mapLocations
    .locator('.spawn-location-card')
    .filter({ hasText: /^Elphidran$/ })
  await expect(palOption).toBeVisible()
  await palOption.click()

  const pointCount = mapLocations.locator('.filter-group__progress')
  await expect
    .poll(async () => Number.parseInt((await pointCount.textContent())?.split(' ')[0] ?? '0', 10))
    .toBeGreaterThan(0)

  await page.getByRole('button', { name: 'World Tree' }).click()
  await expect(page.locator('.zone-btn--active')).toHaveText(/World Tree/)
  await expect
    .poll(async () => Number.parseInt((await pointCount.textContent())?.split(' ')[0] ?? '0', 10))
    .toBeGreaterThan(0)

  await mapLocations.getByRole('tab', { name: 'Human Locations' }).click()
  const humanOption = mapLocations
    .locator('.spawn-location-card')
    .filter({ hasText: 'World Tree Guardian' })
  await expect(humanOption).toBeVisible()
  await humanOption.click()
  await expect
    .poll(async () => Number.parseInt((await pointCount.textContent())?.split(' ')[0] ?? '0', 10))
    .toBeGreaterThan(0)

  const allMarkersButton = page.locator('.map-sidebar__actions .action-btn').first()
  await expect(allMarkersButton).toHaveText('Hide')
  await allMarkersButton.click()
  await expect(allMarkersButton).toHaveText('All')

  await page.getByRole('button', { name: 'Palpagos Islands' }).click()
  await expect(page.locator('.zone-btn--active')).toHaveText(/Palpagos Islands/)
  await expect(page.locator('.palworld-map-marker')).toHaveCount(0)

  await allMarkersButton.click()
  await expect
    .poll(async () => page.locator('.palworld-map-marker').count())
    .toBeGreaterThan(0)
})

test('shows the live player marker only on the matching map zone', async ({ page }) => {
  await page.route('**/player-position/state', async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        status: 'ready',
        processFound: true,
        readAccess: true,
        pid: 123,
        position: {
          gameX: 0,
          gameY: 0,
          gameZ: 0,
          mapZone: 'palpagos',
          updatedAt: '2026-10-02T12:00:00.000Z',
        },
        error: '',
      },
    })
  })

  await page.goto('/map')
  const playerMarker = page.locator('.palworld-player-location')
  await expect(playerMarker).toHaveCount(1)

  await page.getByRole('button', { name: 'World Tree' }).click()
  await expect(playerMarker).toHaveCount(0)

  await page.getByRole('button', { name: 'Palpagos Islands' }).click()
  await expect(playerMarker).toHaveCount(1)
})
