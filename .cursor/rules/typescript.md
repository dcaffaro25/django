# TypeScript Best Practices

## Type Safety

- Always use explicit types for function parameters and return types
- Avoid using `any` - use `unknown` when the type is truly unknown, then narrow it
- Use type guards to narrow types: `typeof`, `instanceof`, or custom type predicates
- Prefer interfaces for object shapes, types for unions/intersections
- Use `const assertions` for literal types: `as const`
- Leverage utility types: `Partial<T>`, `Pick<T, K>`, `Omit<T, K>`, `Record<K, V>`

## Code Organization

- Use strict TypeScript configuration (`strict: true` in tsconfig.json)
- Enable `noImplicitAny`, `strictNullChecks`, and `strictFunctionTypes`
- Organize imports: external libraries first, then internal modules
- Use barrel exports (index.ts) for cleaner imports
- Group related functionality in modules/namespaces when appropriate

## Function & Method Best Practices

- Use arrow functions for callbacks to preserve `this` context
- Prefer function declarations for top-level functions
- Use default parameters instead of `||` or `??` for optional values
- Destructure function parameters when dealing with objects
- Use rest parameters (`...args`) for variadic functions
- Return early to reduce nesting and improve readability

## Async/Await

- Always use `async/await` over promise chains for better readability
- Handle errors with try/catch blocks
- Use `Promise.all()` for parallel async operations
- Use `Promise.allSettled()` when you need all results regardless of failures
- Type async functions explicitly: `async function fetchData(): Promise<DataType>`

## Error Handling

- Create custom error classes extending `Error`
- Use discriminated unions for error handling: `Result<T, E>` pattern
- Never throw strings, always throw Error objects
- Use type guards to check error types: `error instanceof CustomError`

## Generics

- Use descriptive generic names: `T`, `K`, `V` for simple cases, descriptive names for complex ones
- Constrain generics when appropriate: `<T extends BaseType>`
- Use default generic parameters: `<T = string>`
- Avoid over-constraining generics unnecessarily

## Classes & OOP

- Use `private`, `protected`, and `readonly` modifiers appropriately
- Prefer composition over inheritance
- Use abstract classes for base implementations
- Implement interfaces for contracts
- Use getters/setters sparingly, prefer methods for complex logic

## Enums & Constants

- Use `const enum` for compile-time constants when possible
- Prefer string enums over numeric enums for better debugging
- Use `as const` for readonly object literals
- Group related constants in objects with `as const`

## Array & Object Operations

- Use array methods: `map`, `filter`, `reduce`, `find`, `some`, `every`
- Prefer `for...of` loops over traditional for loops
- Use object spread for immutability: `{ ...obj, newProp: value }`
- Use array spread for copying: `[...array]`
- Use `Object.entries()`, `Object.keys()`, `Object.values()` with proper typing

## Null & Undefined Handling

- Use optional chaining: `obj?.prop?.method()`
- Use nullish coalescing: `value ?? defaultValue`
- Use non-null assertion (`!`) sparingly and only when certain
- Prefer explicit null checks over assertions

## Performance

- Avoid unnecessary type assertions
- Use `readonly` arrays when arrays shouldn't be mutated
- Use `Readonly<T>` for immutable object types
- Consider using `satisfies` operator (TypeScript 4.9+) for type checking without widening

## Testing

- Use type-safe test utilities
- Mock with proper types: `jest.fn<() => ReturnType>()`
- Test type boundaries, not just runtime behavior
- Use type-only imports: `import type { Type } from 'module'`

## Documentation

- Use JSDoc comments for public APIs
- Document complex types and generics
- Include examples in documentation for complex functions
- Use `@param`, `@returns`, `@throws` tags

## Common Patterns

- Use discriminated unions for state machines
- Use builder pattern for complex object construction
- Use factory functions for object creation
- Prefer functional programming patterns where appropriate
- Use type predicates for custom type guards

## Avoid

- `any` type (use `unknown` instead)
- Type assertions without validation (`as Type`)
- Non-null assertions without certainty (`!`)
- Mixing `var` with `let`/`const`
- Using `==` instead of `===`
- Mutating function parameters
- Ignoring TypeScript errors with `@ts-ignore` (use `@ts-expect-error` with explanation)

