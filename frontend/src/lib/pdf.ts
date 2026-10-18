/** Export an element as an A4 PDF. html2pdf is loaded on demand to keep the bundle small. */
export async function downloadPdf(element: HTMLElement, filename = "tripmate-travel-plan.pdf") {
  const { default: html2pdf } = await import("html2pdf.js");

  await html2pdf()
    .set({
      margin: 0.5,
      filename,
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
      jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
    })
    .from(element)
    .save();
}
