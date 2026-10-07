/* Copyright 2026 Ib Helmer Nielsen · SPDX-License-Identifier: Apache-2.0 */
"use strict";

function toggleSection(section, visible) {
  if (!section) return;
  section.hidden = !visible;
  section.querySelectorAll("input,select,textarea").forEach((input) => {
    input.disabled = !visible;
  });
}

const application = document.getElementById("application-form");
if (application) {
  const get = (name) => application.elements.namedItem(name);
  if (new URLSearchParams(window.location.search).get("type") === "access") get("request_type").value = "access";
  const update = () => {
    const isStudent = get("applicant_role").value === "student";
    const isVM = get("request_type").value === "vm";
    toggleSection(document.getElementById("class-section"), isStudent);
    get("class_name").required = isStudent;
    toggleSection(document.getElementById("vm-section"), isVM);
    toggleSection(document.getElementById("access-section"), !isVM);
    ["os_family", "os_version", "cpu_cores", "ram_gib", "storage_gib"].forEach((name) => {get(name).required = isVM;});
    get("access_scope").required = !isVM;
    document.getElementById("summary-type").textContent = isVM ? "Virtuel maskine" : "Adgang til Proxmox";
    for (const [key, field, unit] of [["cpu", "cpu_cores", "vCPU"], ["ram", "ram_gib", "GiB"], ["storage", "storage_gib", "GiB"]]) {
      document.getElementById(`summary-${key}-row`).hidden = !isVM;
      document.getElementById(`summary-${key}`).textContent = `${get(field).value || "—"} ${unit}`;
    }
    const start = Date.parse(`${get("starts_on").value}T00:00:00Z`);
    const end = Date.parse(`${get("ends_on").value}T00:00:00Z`);
    const days = Math.round((end - start) / 86400000) + 1;
    document.getElementById("summary-duration").textContent = Number.isFinite(days) && days > 0 ? `${days} dage` : "Vælg datoer";
    if (get("starts_on").value) get("ends_on").min = get("starts_on").value;
  };
  application.addEventListener("input", update);
  application.addEventListener("change", update);
  update();
}

const actionForm = document.getElementById("case-action-form");
if (actionForm && document.getElementById("action")) {
  const updateAction = () => {
    const action = actionForm.elements.namedItem("action").value;
    actionForm.querySelectorAll("[data-action-section]").forEach((section) => toggleSection(section, section.dataset.actionSection === action));
    const publicNote = actionForm.elements.namedItem("public_note");
    const internalNote = actionForm.elements.namedItem("internal_note");
    publicNote.required = ["reject", "close", "extend"].includes(action);
    publicNote.disabled = action === "archive";
    internalNote.required = action === "archive";
    for (const name of ["identity_verified", "decommissioned", "assigned_node", "assigned_vmid", "assigned_account", "new_ends_on"]) {
      const input = actionForm.elements.namedItem(name);
      if (input) input.required = !input.disabled;
    }
  };
  actionForm.elements.namedItem("action").addEventListener("change", updateAction);
  updateAction();
}

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const input = document.getElementById(button.dataset.copyTarget);
    try {
      await navigator.clipboard.writeText(input.value);
      button.textContent = "Kopieret ✓";
    } catch {
      input.focus(); input.select();
      button.textContent = "Tryk Ctrl+C / ⌘C";
    }
  });
});
document.querySelectorAll("[data-print]").forEach((button) => button.addEventListener("click", () => window.print()));
// This is a convenience only: server-side idempotency protects against duplicate submissions.
document.querySelectorAll("form").forEach((form) => form.addEventListener("submit", () => {
  const button = form.querySelector("[data-submit-once]");
  if (button) {
    button.disabled = true;
    button.textContent = "Gemmer …";
    setTimeout(() => {button.disabled = false; button.textContent = "Prøv at sende igen";}, 12000);
  }
}));
