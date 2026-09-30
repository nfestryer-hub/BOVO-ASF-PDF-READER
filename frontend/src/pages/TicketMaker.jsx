import React, { useRef, useState } from "react";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import { toast } from "sonner";
import { Download, RotateCcw, FileText } from "lucide-react";
import TicketDoc from "@/components/TicketDoc";

const DEFAULTS = {
  bl: "BL 9848",
  nPesee: "904212",
  date: "13/08/2026",
  heP1: "13:43",
  heP2: "15:04",
  barige: "8118",
  nCamion: "DX-668-GY",
  client: "7 BOVO",
  zone: "Aucune",
  provenance: "85961 ASF AIRE TRIBAULOU CAHORS",
  produit: "1 VIDANGE",
  fPoids: "33 950",
  fDsd: "0",
  p2Poids: "22 950",
  p2Dsd: "0",
  poidsNet: "10 000",
};

export default function TicketMaker() {
  const [data, setData] = useState(DEFAULTS);
  const [filename, setFilename] = useState("9848");
  const [saving, setSaving] = useState(false);
  const printRef = useRef(null);

  const update = (k, v) => setData((d) => ({ ...d, [k]: v }));

  const reset = () => {
    setData(DEFAULTS);
    setFilename("9848");
    toast.info("Ticket réinitialisé");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      const el = printRef.current;
      const canvas = await html2canvas(el, {
        scale: 2,
        backgroundColor: "#ffffff",
        logging: false,
      });
      const imgData = canvas.toDataURL("image/png");
      const wMm = 80;
      const hMm = (canvas.height / canvas.width) * wMm;
      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: [wMm, hMm] });
      pdf.addImage(imgData, "PNG", 0, 0, wMm, hMm);
      const clean =
        (filename || "").toString().trim().replace(/[^\w\-]/g, "_") || "ticket";
      pdf.save(`${clean}.pdf`);
      toast.success(`PDF enregistré : ${clean}.pdf`);
    } catch (e) {
      console.error(e);
      toast.error("Erreur lors de la génération du PDF");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100" style={{ fontFamily: "Inter, sans-serif" }}>
      {/* Header */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white">
            <FileText size={20} />
          </div>
          <div>
            <h1 className="text-lg font-bold leading-tight text-slate-900">
              Générateur de tickets de pesée
            </h1>
            <p className="text-xs text-slate-500">
              Remplissez les champs surlignés, puis enregistrez au format PDF
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-5xl gap-6 px-5 py-8 lg:grid-cols-[1fr_320px]">
        {/* Ticket éditable */}
        <section className="flex flex-col items-center">
          <div className="mb-4 self-stretch rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-center text-sm text-amber-800">
            Les champs <span className="rounded bg-yellow-300 px-1 font-semibold">surlignés en jaune</span> sont modifiables. Le reste de la mise en page reste fixe.
          </div>
          <div
            className="rounded-sm bg-white shadow-xl"
            style={{ boxShadow: "0 10px 40px rgba(0,0,0,0.12)" }}
          >
            <TicketDoc data={data} editable onChange={update} />
          </div>
        </section>

        {/* Panneau actions */}
        <aside className="lg:sticky lg:top-8 self-start">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Enregistrer
            </h2>

            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Nom du fichier
            </label>
            <div className="mb-4 flex items-center rounded-lg border border-slate-300 bg-white px-3 focus-within:ring-2 focus-within:ring-slate-900">
              <input
                data-testid="filename-input"
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                placeholder="9848"
                className="w-full bg-transparent py-2.5 text-sm outline-none"
              />
              <span className="text-sm text-slate-400">.pdf</span>
            </div>

            <button
              data-testid="save-pdf-button"
              onClick={handleSave}
              disabled={saving}
              className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 py-3 text-sm font-semibold text-white transition-colors hover:bg-slate-700 disabled:opacity-60"
            >
              <Download size={18} />
              {saving ? "Génération…" : "Enregistrer sous PDF"}
            </button>

            <button
              data-testid="reset-button"
              onClick={reset}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
            >
              <RotateCcw size={16} />
              Réinitialiser
            </button>

            <p className="mt-4 text-xs leading-relaxed text-slate-400">
              Format ticket : 80 mm de large (rouleau de caisse). La hauteur s'adapte automatiquement au contenu.
            </p>
          </div>
        </aside>
      </main>

      {/* Version imprimable hors écran (texte propre, sans surlignage) */}
      <div style={{ position: "absolute", left: "-10000px", top: 0 }} aria-hidden="true">
        <div ref={printRef}>
          <TicketDoc data={data} editable={false} />
        </div>
      </div>
    </div>
  );
}
