/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DEFAULT_TENANT?: string
  readonly VITE_DEV_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module "html2pdf.js" {
  interface Html2PdfWorker {
    set(opts: Record<string, unknown>): Html2PdfWorker
    from(element: HTMLElement | string): Html2PdfWorker
    save(filename?: string): Promise<void>
    toPdf(): Html2PdfWorker
    output(type?: string): Promise<unknown>
  }
  function html2pdf(element?: HTMLElement | string): Html2PdfWorker
  export default html2pdf
}
