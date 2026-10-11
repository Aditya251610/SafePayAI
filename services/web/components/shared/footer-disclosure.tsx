// Footer disclosure required on every page (spec.md sec 5, prd.md
// REQ-WB-004). Exact wording - do not paraphrase or strengthen.
export function FooterDisclosure() {
  return (
    <footer className="w-full border-t px-4 py-6 text-center text-xs text-muted-foreground">
      <p>Not affiliated with or endorsed by PayPal.</p>
    </footer>
  );
}
