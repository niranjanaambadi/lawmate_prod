declare module "html-to-docx" {
  function HTMLtoDOCX(
    htmlString: string,
    headerHTMLString: string | null,
    options?: Record<string, unknown>,
    footerHTMLString?: string | null,
  ): Promise<Blob | Buffer>;

  export default HTMLtoDOCX;
}
