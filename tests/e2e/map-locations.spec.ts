import { expect, test } from '@playwright/test'

test('shows Pal and human locations and keeps map filters synchronized across zones', async ({
  page,
}) => {
  await page.goto('/map')

  const mapLocations = page.locator('.map-locations-group')
  await expect(mapLocations.getByRole('tab', { name: 'Pal Locations' })).toBeVisible()
  await expect(page.locator('.map-sidebar .filter-group').last()).toHaveClass(
    /map-locations-group/,
  )
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
  let gameX = 0
  let positionRequests = 0
  await page.route('**/player-position/state', async (route) => {
    positionRequests += 1
    await route.fulfill({
      json: {
        ok: true,
        status: 'ready',
        processFound: true,
        readAccess: true,
        pid: 123,
        position: {
          gameX,
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

  const initialRequests = positionRequests
  gameX = 200_000
  await expect.poll(() => positionRequests).toBeGreaterThan(initialRequests)
  await expect.poll(() =>
    playerMarker.evaluate((marker) => {
      const markerRect = marker.getBoundingClientRect()
      const mapRect = marker.closest('.palworld-map')?.getBoundingClientRect()
      if (!mapRect) return Number.POSITIVE_INFINITY
      return Math.hypot(
        markerRect.left + markerRect.width / 2 - (mapRect.left + mapRect.width / 2),
        markerRect.top + markerRect.height / 2 - (mapRect.top + mapRect.height / 2),
      )
    }),
  ).toBeLessThan(3)

  await page.getByRole('button', { name: 'World Tree' }).click()
  await expect(playerMarker).toHaveCount(0)

  await page.getByRole('button', { name: 'Palpagos Islands' }).click()
  await expect(playerMarker).toHaveCount(1)
})
