// Wrangler Text module rule (see wrangler.jsonc) makes *.html a string import.
declare module "*.html" {
  const content: string;
  export default content;
}
