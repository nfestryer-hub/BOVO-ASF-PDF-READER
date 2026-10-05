import React, { forwardRef } from "react";
import { TICKET_BG, TICKET_W, TICKET_H } from "@/ticketBg";

const TICKET_PX = 330;
const HEIGHT_PX = Math.round(TICKET_PX * (TICKET_H / TICKET_W));

// Zones blanches éditables, positionnées sur le scan (left/top/width en %, height/fontSize en px)
export const FIELDS = [
  { id: "nPesee", left: 34.3, top: 19.6, w: 15.8, h: 19, fs: 13, align: "center" },
  { id: "date", left: 67.8, top: 19.6, w: 24.0, h: 19, fs: 12, align: "center" },
  { id: "heP1", left: 36.0, top: 25.6, w: 15.0, h: 18, fs: 13, align: "center" },
  { id: "heP2", left: 69.2, top: 25.6, w: 15.0, h: 18, fs: 13, align: "center" },
  { id: "nCamion", left: 58.5, top: 31.6, w: 21.5, h: 19, fs: 12, align: "center" },
  { id: "client", left: 28.7, top: 37.6, w: 22.0, h: 18, fs: 13, align: "left" },
  { id: "zone", left: 52.7, top: 40.7, w: 28.0, h: 17, fs: 13, align: "center" },
  { id: "provenance", left: 7.8, top: 55.7, w: 90.0, h: 18, fs: 11, align: "center" },
  { id: "produit", left: 32.0, top: 67.8, w: 26.0, h: 18, fs: 13, align: "center" },
  { id: "fPoids", left: 19.5, top: 75.2, w: 36.0, h: 23, fs: 19, align: "left", bold: true },
  { id: "p2Poids", left: 19.5, top: 81.2, w: 36.0, h: 23, fs: 19, align: "left", bold: true },
  { id: "poidsNet", left: 32.2, top: 93.2, w: 24.8, h: 23, fs: 19, align: "center", bold: true },
];

const TicketDoc = forwardRef(({ data, editable = false, onChange }, ref) => {
  const baseStyle = (f) => ({
    position: "absolute",
    left: `${f.left}%`,
    top: `${f.top}%`,
    width: `${f.w}%`,
    height: `${f.h}px`,
    lineHeight: `${f.h}px`,
    fontSize: `${f.fs}px`,
    textAlign: f.align,
    fontFamily: '"TicketMono", "Roboto Mono", "Courier New", monospace',
    fontWeight: f.bold ? 700 : 400,
    color: "#000000",
    background: "#ffffff",
    border: "none",
    outline: "none",
    padding: "0 1px",
    margin: 0,
    overflow: "hidden",
    whiteSpace: "nowrap",
    boxSizing: "border-box",
  });

  return (
    <div
      className="scan-ticket"
      ref={ref}
      data-testid="ticket-document"
      style={{
        position: "relative",
        width: `${TICKET_PX}px`,
        height: `${HEIGHT_PX}px`,
        backgroundImage: `url(${TICKET_BG})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: "100% 100%",
        backgroundColor: "#ffffff",
      }}
    >
      {FIELDS.map((f) => {
        const v = data[f.id] ?? "";
        if (!editable) {
          return (
            <div key={f.id} style={baseStyle(f)}>
              {v}
            </div>
          );
        }
        return (
          <input
            key={f.id}
            data-testid={`field-${f.id}`}
            className="tk-field"
            spellCheck={false}
            value={v}
            onChange={(e) => onChange && onChange(f.id, e.target.value)}
            style={{
              ...baseStyle(f),
              boxShadow: "inset 0 0 0 1px rgba(37,99,235,0.18)",
            }}
          />
        );
      })}
    </div>
  );
});

TicketDoc.displayName = "TicketDoc";

export default TicketDoc;
