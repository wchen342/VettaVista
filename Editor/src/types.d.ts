declare global { export type AssertionType<T> = [T] extends [UnionToIntersection<T>] ? T : never; }

type UnionToIntersection<U> =
    (U extends any ? (k: U) => void : never) extends ((k: infer I) => void) ? I : never;