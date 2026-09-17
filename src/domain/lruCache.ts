export class LruCache<K, V> {
  private readonly entries = new Map<K, V>()

  constructor(readonly capacity: number) {
    if (!Number.isInteger(capacity) || capacity < 1) throw new Error('Invalid cache capacity')
  }

  get size(): number {
    return this.entries.size
  }

  get(key: K): V | undefined {
    const value = this.entries.get(key)
    if (value === undefined) return undefined
    this.entries.delete(key)
    this.entries.set(key, value)
    return value
  }

  set(key: K, value: V): void {
    this.entries.delete(key)
    this.entries.set(key, value)
    while (this.entries.size > this.capacity) {
      const oldest = this.entries.keys().next().value
      if (oldest === undefined) break
      this.entries.delete(oldest)
    }
  }

  has(key: K): boolean {
    return this.entries.has(key)
  }

  clear(): void {
    this.entries.clear()
  }
}
