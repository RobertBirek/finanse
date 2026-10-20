import "@testing-library/jest-dom/vitest";

// jsdom has no native dialog implementation. Browser focus/inert behavior is
// checked separately in Chromium; this shim only mirrors the open state.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
}
