// Files imported with ?raw (the brand glyph) arrive as their text, inlined at build time.
declare module '*?raw' {
  const text: string
  export default text
}
