export type CakeKey =
  | 'wheat'
  | 'berry'
  | 'milk'
  | 'egg'
  | 'tomato'
  | 'lettuce'
  | 'mushroom'
  | 'cavern'
  | 'cotton'
  | 'potato'
  | 'onion'
  | 'carrot'
  | 'caramel'
  | 'mammorest'
  | 'flour'
  | 'honey'

export type CakeValues = Record<CakeKey, number>

export interface CakeIngredient {
  key: CakeKey
  label: string
  per: number
  stock: CakeKey
  price: CakeKey
}

export interface CakeRecipe {
  id: string
  label: string
  flourPer: number
  honeyPer: number
  note: string
  ingredients: CakeIngredient[]
}

export const priceDefaults: CakeValues = {
  wheat: 59,
  berry: 42,
  milk: 170,
  egg: 170,
  tomato: 80,
  lettuce: 80,
  mushroom: 50,
  cavern: 80,
  cotton: 100,
  potato: 50,
  onion: 50,
  carrot: 50,
  caramel: 200,
  mammorest: 800,
  flour: 0,
  honey: 0,
}

export const emptyStock: CakeValues = Object.fromEntries(
  Object.keys(priceDefaults).map((key) => [key, 0]),
) as unknown as CakeValues

const ingredient = (
  key: CakeKey,
  label: string,
  per: number,
  stock: CakeKey = key,
): CakeIngredient => ({ key, label, per, stock, price: key })

export const cakeRecipes: CakeRecipe[] = [
  {
    id: 'cake',
    label: 'Cake',
    flourPer: 1,
    honeyPer: 2,
    note: '1 Flour, 8 Red Berries, 7 Milk, 8 Eggs, and 2 Honey.',
    ingredients: [
      ingredient('berry', 'Red Berries', 8),
      ingredient('milk', 'Milk', 7),
      ingredient('egg', 'Egg', 8),
    ],
  },
  {
    id: 'mushroom',
    label: 'Mushroom Cake',
    flourPer: 1,
    honeyPer: 2,
    note: '1 Flour, 5 Mushrooms, 3 Cavern Mushrooms, 8 Eggs, and 2 Honey.',
    ingredients: [
      ingredient('mushroom', 'Mushroom', 5),
      ingredient('cavern', 'Cavern Mushroom', 3),
      ingredient('egg', 'Egg', 8),
    ],
  },
  {
    id: 'vegetable',
    label: 'Vegetable Cake',
    flourPer: 1,
    honeyPer: 4,
    note: '1 Flour, 8 Tomatoes, 7 Lettuce, 8 Eggs, and 4 Honey.',
    ingredients: [
      ingredient('tomato', 'Tomato', 8),
      ingredient('lettuce', 'Lettuce', 7),
      ingredient('egg', 'Egg', 8),
    ],
  },
  {
    id: 'extravagant',
    label: 'Extravagant Vegetable Cake',
    flourPer: 1,
    honeyPer: 0,
    note: '1 Flour, 8 Cotton Candy, 10 Potatoes, 6 Onions, and 8 Carrots.',
    ingredients: [
      ingredient('cotton', 'Cotton Candy', 8),
      ingredient('potato', 'Potato', 10),
      ingredient('onion', 'Onion', 6),
      ingredient('carrot', 'Carrot', 8),
    ],
  },
  {
    id: 'special',
    label: 'Special Cake',
    flourPer: 1,
    honeyPer: 0,
    note: '1 Flour, 8 Caramel Cotton Candy, 15 Milk, 15 Eggs, and 2 Mammorest Meat.',
    ingredients: [
      ingredient('caramel', 'Caramel Cotton Candy', 8),
      ingredient('milk', 'Milk', 15),
      ingredient('egg', 'Egg', 15),
      ingredient('mammorest', 'Mammorest Meat', 2),
    ],
  },
]

export interface CakeCalculation {
  maximum: number
  amount: number
  shortfall: number
  spent: number
  remaining: number
  unitCost: number
  honeyCap: number | null
  wheatNeeded: number
  purchases: Partial<CakeValues>
}

function purchasesFor(
  amount: number,
  recipe: CakeRecipe,
  stock: CakeValues,
  prices: CakeValues,
): { values: Partial<CakeValues>; spent: number } {
  const values: Partial<CakeValues> = {}
  let spent = 0
  for (const item of recipe.ingredients) {
    const quantity = Math.max(0, amount * item.per - stock[item.stock])
    values[item.key] = quantity
    spent += quantity * prices[item.price]
  }
  return { values, spent }
}

export function calculateCakes(
  gold: number,
  target: number,
  recipe: CakeRecipe,
  stock: CakeValues,
  prices: CakeValues,
): CakeCalculation {
  const unitCost =
    recipe.ingredients.reduce((sum, item) => sum + item.per * prices[item.price], 0)
  const honeyCap =
    recipe.honeyPer > 0 && stock.honey > 0 ? Math.floor(stock.honey / recipe.honeyPer) : null
  const flourCap = Math.floor(stock.flour / recipe.flourPer)
  let high =
    flourCap +
    recipe.ingredients.reduce((sum, item) => sum + Math.floor(stock[item.stock] / item.per), 2) +
    (unitCost > 0 ? Math.floor(gold / unitCost) + 2 : 100_000)
  if (honeyCap !== null) high = Math.min(high, honeyCap)
  high = Math.min(Math.max(high, 0), 1_000_000)
  let low = 0
  let maximum = 0
  while (low <= high) {
    const middle = (low + high) >> 1
    const purchase = purchasesFor(middle, recipe, stock, prices)
    if (
      purchase.spent <= gold &&
      middle <= flourCap &&
      (honeyCap === null || middle <= honeyCap)
    ) {
      maximum = middle
      low = middle + 1
    } else {
      high = middle - 1
    }
  }
  const amount = target > 0 ? Math.min(target, maximum) : maximum
  const purchase = purchasesFor(amount, recipe, stock, prices)
  const wheatNeeded = Math.max(0, (target - stock.flour) * 3)
  return {
    maximum,
    amount,
    shortfall: Math.max(0, target - maximum),
    spent: purchase.spent,
    remaining: Math.max(0, gold - purchase.spent),
    unitCost,
    honeyCap,
    wheatNeeded,
    purchases: purchase.values,
  }
}
