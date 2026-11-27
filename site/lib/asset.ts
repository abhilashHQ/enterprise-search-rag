/** A path under public/, with the GitHub Pages base path in front when the site is built for Pages. */
export const asset = (path: string) => `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}${path}`
