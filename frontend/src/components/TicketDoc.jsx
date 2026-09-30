import React, { forwardRef } from "react";

const renderZeros = (v) =>
  String(v ?? "")
    .split(/(0)/)
    .map((p, i) => (p === "0" ? <span key={i} className="tk-zero">0</span> : p || null));

const TicketDoc = forwardRef(({ data, editable = false, onChange }, ref) => {
  const Field = ({ k, min = 2, blue = false, className = "" }) => {
    const v = data[k] ?? "";
    if (!editable) {
      return (
        <span
          className={`tk-val ${className}`}
          style={blue ? { color: "#1d4ed8" } : undefined}
        >
          {renderZeros(v)}
        </span>
      );
    }
    return (
      <input
        data-testid={`field-${k}`}
        className={`tk-input ${className}`}
        style={{
          width: `${Math.max((v || "").length, min) + 1}ch`,
          ...(blue ? { color: "#1d4ed8" } : {}),
        }}
        value={v}
        spellCheck={false}
        onChange={(e) => onChange && onChange(k, e.target.value)}
      />
    );
  };

  return (
    <div className="ticket" ref={ref} data-testid="ticket-document">
      <div className="tk-center tk-strong tk-mx tk-hdr">***&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ASTEO&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;***</div>

      <div className="tk-gap" />

      <div className="tk-center">51 Chemin de Chantelle</div>
      <div className="tk-center">CS 82341</div>
      <div className="tk-center">{renderZeros("31021 TOULOUSE CEDEX 2")}</div>

      <div className="tk-gap" />

      <div className="tk-two">
        <span className="tk-seg">N Pesee : <Field k="nPesee" min={6} /></span>
        <span className="tk-seg">Date <Field k="date" min={8} /></span>
      </div>

      <div className="tk-gap-sm" />

      <div className="tk-inline">
        <span className="tk-seg">He P1 <Field k="heP1" min={5} /></span>
        <span className="tk-seg">He P2 <Field k="heP2" min={5} /></span>
      </div>

      <div className="tk-gap-sm" />

      <div className="tk-two">
        <span className="tk-seg">Badge : <Field k="barige" min={4} /></span>
        <span className="tk-seg">N Camion : <Field k="nCamion" min={7} /></span>
      </div>

      <div className="tk-gap" />

      <div className="tk-client">Client : <Field k="client" min={5} /></div>
      <div className="tk-zone">Zone : <Field k="zone" min={5} /></div>

      <div className="tk-gap" />

      <div className="tk-fiche">
        <span>Fiche</span>
        <span>Provenance</span>
        <span>Adresse</span>
        <span>Ville</span>
      </div>

      <div className="tk-gap-sm" />

      <div className="tk-center">
        <Field k="provenance" min={20} className="tk-prov" />
      </div>

      <div className="tk-gap" />

      <div className="tk-center tk-strong">* * * PRODUIT * * *</div>

      <div className="tk-gap-sm" />

      <div className="tk-center">
        <Field k="produit" min={9} />
      </div>

      <div className="tk-gap" />

      <div className="tk-weights">
        <div className="tk-wrow">
          <span className="tk-wlabel tk-mx">P1:</span>
          <Field k="fPoids" min={6} className="tk-mx" /> <span className="tk-mx">kg</span>
          <span className="tk-dsd">DSD :</span> <Field k="fDsd" min={1} />
        </div>
        <div className="tk-wrow">
          <span className="tk-wlabel tk-mx">P2:</span>
          <Field k="p2Poids" min={6} className="tk-mx" /> <span className="tk-mx">kg</span>
          <span className="tk-dsd">DSD :</span> <Field k="p2Dsd" min={1} />
        </div>
      </div>

      <div className="tk-gap" />

      <div className="tk-center tk-strong">* * * POIDS NET * * *</div>

      <div className="tk-gap-sm" />

      <div className="tk-center">
        <Field k="poidsNet" min={5} className={`tk-mx ${editable ? "tk-net-input" : "tk-net-num"}`} /> kg
      </div>
    </div>
  );
});

TicketDoc.displayName = "TicketDoc";

export default TicketDoc;
