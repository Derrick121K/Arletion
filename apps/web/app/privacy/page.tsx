export default function PrivacyNoticePage() {
  return <main className="content" style={{ maxWidth: 820, margin: "0 auto", paddingTop: 38 }}>
    <div className="eyebrow">ARLETION · PRIVACY</div>
    <h1 className="h1">Privacy notice for debt-review enquiries</h1>
    <p className="subtitle">This notice explains how JMSE KAPA HOLDINGS (PTY) LTD, operating the Arletion service, handles information submitted through the voluntary debt-review enquiry form.</p>
    <section className="card" style={{ display: "grid", gap: 14, marginTop: 22 }}>
      <h2 className="sectiontitle">Information collected</h2>
      <p className="sectiondesc">The form asks for your name, at least one contact method, town or province, the type of guidance requested, your preferred response channel and consent choices. It does not ask for your South African ID number, bank details, account numbers, creditor list, salary or detailed financial history.</p>
      <h2 className="sectiontitle">Why it is used</h2>
      <p className="sectiondesc">Your details are used to receive and respond to your enquiry. Optional marketing is a separate choice and is not required to submit an enquiry. Arletion does not run a credit check, place anyone under debt review, or guarantee approval, clearance or removal of a debt-review status.</p>
      <h2 className="sectiontitle">Storage and access</h2>
      <p className="sectiondesc">Consumer contact details are encrypted before storage. Access to decrypt them requires a separate credential. The enquiry list shows protected metadata rather than names, phone numbers or email addresses. Access controls and the storage environment must be reviewed before public intake is activated.</p>
      <h2 className="sectiontitle">Retention</h2>
      <p className="sectiondesc">The configured default retention period is 90 days, within a permitted configuration range of 30 to 365 days. The system records an expiry date. A verified scheduled deletion process and backup-recovery checks are required before public intake can be enabled; an expiry date alone does not delete information.</p>
      <h2 className="sectiontitle">Sharing</h2>
      <p className="sectiondesc">Submitting this form does not automatically share your information with a debt counsellor or another organisation. Any referral must be separately explained and authorised before information is transferred.</p>
      <h2 className="sectiontitle">Your choices and rights</h2>
      <p className="sectiondesc">You may choose not to submit the form, leave the optional marketing choice unticked, or withdraw marketing consent later. You may also request access to or correction of your information, object to processing, or ask about deletion, subject to applicable legal requirements. Contact JMSE KAPA HOLDINGS through its official business contact channel to make a privacy request.</p>
      <h2 className="sectiontitle">Marketing</h2>
      <p className="sectiondesc">Marketing consent is optional and separate from consent to respond to your enquiry. No marketing messages are sent simply because an enquiry was submitted. A withdrawal must be honoured and recorded.</p>
      <h2 className="sectiontitle">Important</h2>
      <p className="sectiondesc">Arletion is not the National Credit Regulator and is not a debt counsellor merely by receiving an enquiry. Verify any debt counsellor on the official NCR register. Do not submit passwords, PINs or sensitive financial records through this form.</p>
      <a className="link" href="https://www.ncr.org.za/register_of_registrants/registered_dc.php" target="_blank" rel="noreferrer">Official NCR register of debt counsellors ↗</a>
      <a className="link" href="/enquire">Return to the enquiry form</a>
    </section>
    <p className="sourcedesc" style={{ marginTop: 18 }}>This notice is a product notice for the current enquiry workflow and should be reviewed by the responsible party / Information Officer and South African privacy counsel before public launch.</p>
  </main>;
}
