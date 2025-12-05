# React Best Practices

## Component Structure

- Use functional components with hooks (prefer over class components)
- Keep components small and focused (Single Responsibility Principle)
- Extract reusable logic into custom hooks
- Use composition over inheritance
- Split large components into smaller, manageable pieces
- One component per file, named export for the component

## Hooks

- Only call hooks at the top level (not in loops, conditions, or nested functions)
- Use `useState` for local component state
- Use `useEffect` for side effects (API calls, subscriptions, DOM manipulation)
- Always include dependencies in `useEffect` dependency array
- Use `useCallback` to memoize functions passed as props
- Use `useMemo` to memoize expensive calculations
- Create custom hooks for reusable stateful logic
- Use `useRef` for mutable values that don't trigger re-renders
- Use `useContext` for sharing data without prop drilling

## State Management

- Lift state up to the nearest common ancestor when needed
- Use local state (`useState`) when state is component-specific
- Use Context API for global state that doesn't change frequently
- Consider state management libraries (Redux, Zustand) for complex state
- Avoid prop drilling - use Context or state management library
- Keep state as close to where it's used as possible

## Props & Component API

- Use TypeScript/PropTypes for prop validation
- Destructure props in function parameters
- Use default parameters for optional props
- Keep prop interfaces/types near the component
- Avoid passing too many props (consider using objects or Context)
- Use children prop for composition
- Prefer explicit prop names over boolean props when meaning is unclear

## Performance Optimization

- Use `React.memo` for components that render frequently with same props
- Use `useMemo` for expensive computations
- Use `useCallback` for functions passed to child components
- Implement virtual scrolling for long lists (react-window, react-virtualized)
- Code split with `React.lazy()` and `Suspense`
- Avoid creating objects/functions in render (move to useMemo/useCallback)
- Use `key` prop correctly for list items (stable, unique identifiers)

## Event Handling

- Use arrow functions or `useCallback` for event handlers
- Avoid inline arrow functions in JSX when passing to memoized components
- Use event delegation when appropriate
- Prevent default behavior explicitly when needed
- Use synthetic events properly (React's event system)

## Conditional Rendering

- Use ternary operators for simple conditions
- Use `&&` operator carefully (watch for falsy values like 0)
- Extract complex conditions into variables or functions
- Use early returns in components for cleaner code
- Consider using render props or custom hooks for complex logic

## Lists & Keys

- Always provide a stable, unique `key` prop for list items
- Use IDs from data, not array indices (unless list is static)
- Keys should be unique among siblings
- Don't use keys for component logic

## Forms

- Use controlled components for form inputs
- Handle form state with `useState` or form libraries (react-hook-form, formik)
- Validate input on change and/or submit
- Provide clear error messages
- Disable submit button during submission
- Reset form after successful submission

## API Calls & Data Fetching

- Use `useEffect` for data fetching on component mount
- Clean up subscriptions and async operations in `useEffect` cleanup
- Handle loading, error, and success states
- Use libraries like React Query or SWR for advanced data fetching
- Avoid fetching data in render - use `useEffect` or event handlers
- Cancel requests when component unmounts (AbortController)

## Error Handling

- Use Error Boundaries for catching component errors
- Handle API errors gracefully with user-friendly messages
- Log errors appropriately (don't expose sensitive info)
- Provide fallback UI for error states
- Use try/catch in async functions

## Styling

- Use CSS Modules, styled-components, or Tailwind CSS for scoped styles
- Keep styles close to components
- Use consistent naming conventions (BEM, camelCase, etc.)
- Avoid inline styles for complex styling (use for dynamic values)
- Use CSS variables for theming
- Make components responsive and accessible

## Accessibility

- Use semantic HTML elements
- Add `aria-label` for icon-only buttons
- Ensure keyboard navigation works
- Use proper heading hierarchy (h1, h2, h3)
- Provide alt text for images
- Ensure sufficient color contrast
- Use `role` attributes when semantic HTML isn't available
- Test with screen readers

## Testing

- Write unit tests for components with React Testing Library
- Test user interactions, not implementation details
- Use `data-testid` sparingly (prefer accessible queries)
- Test error states and edge cases
- Mock external dependencies (API calls, modules)
- Keep tests simple and focused

## Code Organization

- Group related files in feature folders
- Use index files for clean imports
- Separate concerns: components, hooks, utils, types
- Keep utility functions pure and testable
- Use absolute imports with path aliases
- Organize imports: external, internal, relative

## TypeScript with React

- Use `React.FC` or explicit return types for components
- Type props with interfaces or types
- Use generic types for reusable components
- Type event handlers: `React.ChangeEvent<HTMLInputElement>`
- Use `React.ReactNode` for children prop
- Avoid `any` - use proper types or `unknown`

## Common Patterns

- Container/Presentational pattern (or hooks for logic separation)
- Render props pattern for reusable logic
- Higher-Order Components (HOCs) when appropriate
- Compound components for related UI elements
- Custom hooks for shared logic

## Best Practices

- Use meaningful component and variable names
- Keep JSX readable - extract complex expressions
- Comment complex logic, not obvious code
- Follow consistent code style (ESLint, Prettier)
- Remove unused imports and variables
- Use constants for magic numbers and strings
- Extract repeated JSX into components or functions

## Avoid

- Mutating state directly (always use setState/useState setter)
- Using array index as key (unless list is static)
- Creating functions/objects in render without memoization
- Overusing `useEffect` (consider if logic belongs elsewhere)
- Prop drilling through many levels
- Mixing concerns (data fetching, UI logic, business logic)
- Ignoring warnings and errors
- Using `dangerouslySetInnerHTML` without sanitization
- Forgetting cleanup in `useEffect`
- Creating components inside other components

## File Naming

- Use PascalCase for component files: `UserProfile.tsx`
- Use camelCase for utility files: `formatDate.ts`
- Use kebab-case for some projects (follow team convention)
- Match file name with default export name

## Dependencies

- Keep dependencies up to date
- Use exact versions in production or lock files
- Remove unused dependencies
- Prefer smaller, focused libraries over large frameworks
- Consider bundle size when adding dependencies

