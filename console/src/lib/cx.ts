/** Conditional class names, kept tiny so the app needs no `clsx` dependency. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
