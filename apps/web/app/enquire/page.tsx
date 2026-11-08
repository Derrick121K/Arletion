"use client";

import { FormEvent, useState } from "react";

const categories = [
  ["considering_debt_review", "I am considering debt review"],
  ["already_under_review", "I am already under debt review"],
  ["application_pending", "I have applied and am waiting for feedback"],
  ["debt_review_assistance", "I need help understanding my current debt-review status"],
  ["completed_debt_review", "I have completed debt review and need status guidance"],
  ["debt_counselling", "I want to speak to a debt counsellor"],
  ["budget_guidance", "I want general budgeting guidance"],
  ["general", "Something else"],
];

export default function DebtReviewEnquiryPage() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState("considering_debt_review");
  const [channel, setChannel] = useState("phone");
  const [marketing, setMarketing] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const body = {
      full_name: String(form.get("full_name") || ""),
      phone: String(form.get("phone") || "") || null,
      email: String(form.get("email") || "") || null,
      province: String(form.get("province") || "") || null,
      locality: String(form.get("locality") || "") || null,
      preferred_channel: channel,
      category,
      processing_consent: form.get("processing_consent") === "on",
      marketing_consent: marketing,
      age_confirmed: form.get("age_confirmed") === "on",
      website: String(form.get("website") || ""),
    };
    try {
      const response = await fetch("/api/public/enquiries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Your enquiry could not be submitted.");
      formElement.reset();
      setMarketing(false);
      setMessage("Your enquiry has been received. A response is not a guarantee of debt-review approval or removal.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Your enquiry could not be submitted.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="content" style={{ maxWidth: 760, margin: "0 auto", paddingTop: 38 }}>
    <div className="eyebrow">ARLETION · PRIVATE ENQUIRY</div>
    <h1 className="h1">Debt-review assistance</h1>
    <p className="subtitle">Tell us what kind of guidance you are looking for. This form is voluntary. It is not a credit check, debt-review application, or a promise that a debt-review status can be changed.</p>
    <form className="card" onSubmit={submit} style={{ display: "grid", gap: 14, marginTop: 22 }}>
      <label>What best describes your situation?
        <select required value={category} onChange={event => setCategory(event.target.value)} style={field}>
          {categories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label>Full name
        <input name="full_name" required minLength={2} maxLength={160} autoComplete="name" style={field} />
      </label>
      <div className="grid2">
        <label>Phone number
          <input name="phone" type="tel" maxLength={32} autoComplete="tel" placeholder="+27..." style={field} />
        </label>
        <label>Email address
          <input name="email" type="email" maxLength={254} autoComplete="email" style={field} />
        </label>
      </div>
      <div className="grid2">
        <label>Town / locality
          <input name="locality" maxLength={120} autoComplete="address-level2" style={field} />
        </label>
        <label>Province
          <select name="province" style={field} defaultValue="Mpumalanga">
            {["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga", "Northern Cape", "North West", "Western Cape"].map(value => <option key={value}>{value}</option>)}
          </select>
        </label>
      </div>
      <label>Preferred response channel
        <select value={channel} onChange={event => setChannel(event.target.value)} style={field}>
          <option value="phone">Phone</option><option value="whatsapp">WhatsApp</option><option value="email">Email</option>
        </select>
      </label>
      <label style={check}><input type="checkbox" name="age_confirmed" required /> I confirm that I am 18 years or older.</label>
      <label style={check}><input type="checkbox" name="processing_consent" required /> I consent to JMSE KAPA HOLDINGS / Arletion using these details only to respond to this enquiry. I have read the <a href="/privacy">Privacy Notice</a>.</label>
      <label style={check}><input type="checkbox" checked={marketing} onChange={event => setMarketing(event.target.checked)} /> I separately agree to receive future marketing messages. This is optional and can be withdrawn.</label>
      <label style={{ position: "absolute", left: "-10000px" }} aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
      <p className="sourcedesc">Do not enter your South African ID number, bank details, passwords, account numbers, creditor lists, salary or detailed financial history. We will not place you under debt review without your informed agreement. Your enquiry is not shared with a debt counsellor unless the appropriate process and permissions are in place.</p>
      <button className="btn" type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit private enquiry"}</button>
      {message && <p role="status" className="sectiondesc">{message}</p>}
      <a className="link" href="/privacy">Read the Arletion privacy notice</a>
      <a className="link" href="https://www.ncr.org.za/register_of_registrants/registered_dc.php" target="_blank" rel="noreferrer">Check the NCR registered debt counsellor directory ↗</a>
    </form>
    <p className="sourcedesc" style={{ marginTop: 18 }}>For an urgent complaint about a credit provider or debt counsellor, contact the National Credit Regulator through its official website. Arletion is not the NCR.</p>
  </main>;
}

const field = { display: "block", width: "100%", padding: "11px 12px", border: "1px solid #e8e3ed", borderRadius: 9, marginTop: 6, background: "#fff", font: "inherit" };
const check = { display: "flex", gap: 9, alignItems: "flex-start", fontSize: 12, lineHeight: 1.5 };
