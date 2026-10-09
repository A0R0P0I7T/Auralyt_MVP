let currentBrandId = null;
let currentRunId = null;
let pollInterval = null;
let profileData = null;
let pagesCurrentPage = 1;

function switchTab(tabName) {
  document.querySelectorAll(".tab-content").forEach(el => el.style.display = "none");
  document.querySelectorAll(".nav-btn").forEach(el => el.classList.remove("active"));

  const targetTab = document.getElementById(`tab-${tabName}`);
  if (targetTab) targetTab.style.display = "block";

  const btn = Array.from(document.querySelectorAll(".nav-btn")).find(b => b.getAttribute("onclick")?.includes(tabName));
  if (btn) btn.classList.add("active");

  if (tabName === "profile" && currentBrandId) loadBrandProfile(currentBrandId);
  if (tabName === "facts" && currentBrandId) renderFactsList();
  if (tabName === "pages" && currentBrandId) loadCrawledPages(1);
}

async function handleOnboard(event) {
  event.preventDefault();
  const errorBox = document.getElementById("onboard-error");
  errorBox.style.display = "none";

  const payload = {
    website_url: document.getElementById("website_url").value.trim(),
    business_name: document.getElementById("business_name").value.trim() || null,
    industry: document.getElementById("industry").value.trim() || null,
    target_market: document.getElementById("target_market").value.trim() || null,
    language: document.getElementById("language").value.trim() || null,
    page_limit: parseInt(document.getElementById("page_limit").value) || 30
  };

  const startBtn = document.getElementById("start-btn");
  startBtn.disabled = true;
  startBtn.innerText = "Initiating Crawl...";

  try {
    const res = await fetch("/api/brands/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to start profiling.");
    }

    currentBrandId = data.brand_id;
    currentRunId = data.run_id;

    switchTab("progress");
    startRunPolling(currentRunId);
  } catch (err) {
    errorBox.innerText = err.message;
    errorBox.style.display = "block";
  } finally {
    startBtn.disabled = false;
    startBtn.innerText = "🚀 Start Website Profiling";
  }
}

function startRunPolling(runId) {
  if (pollInterval) clearInterval(pollInterval);

  const checkStatus = async () => {
    try {
      const res = await fetch(`/api/brands/profile-runs/${runId}`);
      if (!res.ok) return;
      const run = await res.json();

      updateProgressUI(run);

      if (run.status === "completed" || run.status === "completed_with_warnings" || run.status === "failed") {
        clearInterval(pollInterval);
        document.getElementById("view-profile-btn").style.display = "inline-flex";
      }
    } catch (e) {
      console.error("Poll error:", e);
    }
  };

  checkStatus();
  pollInterval = setInterval(checkStatus, 1500);
}

function updateProgressUI(run) {
  const badge = document.getElementById("run-status-badge");
  badge.innerText = run.status.toUpperCase();
  badge.className = `badge badge-${run.status.replace("_with_warnings", "")}`;

  document.getElementById("stat-discovered").innerText = run.pages_discovered || 0;
  document.getElementById("stat-attempted").innerText = run.pages_attempted || 0;
  document.getElementById("stat-succeeded").innerText = run.pages_succeeded || 0;
  document.getElementById("stat-skipped").innerText = run.pages_skipped || 0;
  document.getElementById("stat-failed").innerText = run.pages_failed || 0;

  if (run.warnings && run.warnings.length > 0) {
    document.getElementById("warnings-section").style.display = "block";
    const wlist = document.getElementById("warnings-list");
    wlist.innerHTML = run.warnings.map(w => `<li>${w}</li>`).join("");
  }
}

async function loadBrandProfile(brandId) {
  try {
    const res = await fetch(`/api/brands/${brandId}/profile`);
    if (!res.ok) return;
    profileData = await res.json();

    document.getElementById("profile-brand-name").innerText = profileData.brand.business_name || profileData.brand.domain;
    document.getElementById("profile-domain").innerText = profileData.brand.domain;
    document.getElementById("profile-version-badge").innerText = `v${profileData.profile_version}`;
    document.getElementById("profile-stat-facts").innerText = profileData.verification_progress.total_facts || 0;
    document.getElementById("profile-stat-verified").innerText = profileData.verification_progress.confirmed_facts || 0;
    document.getElementById("profile-stat-pages").innerText = profileData.coverage_summary.total_pages_crawled || 0;

    // Overview
    document.getElementById("overview-desc").innerText = profileData.business_overview.description || "Website claims and description pending synthesis.";
    document.getElementById("overview-industry").innerText = profileData.business_overview.industry || "Not specified";
    document.getElementById("overview-market").innerText = profileData.business_overview.target_market || "Global";

    // Products
    const prodList = document.getElementById("products-list");
    if (profileData.products_and_services.length === 0) {
      prodList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No products or services detected yet.</div>`;
    } else {
      prodList.innerHTML = profileData.products_and_services.map(p => {
        const val = typeof p.value === "object" ? (p.value.name + (p.value.description ? ` — ${p.value.description}` : "")) : p.value;
        return `
          <div style="background: #0f172a; padding: 0.75rem 1rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 0.95rem;">${escapeHtml(val)}</span>
            <button class="btn btn-secondary btn-sm" onclick="openEvidenceModal('${p.fact_id}')">Inspect Source</button>
          </div>
        `;
      }).join("");
    }

    // Audiences
    const audList = document.getElementById("audience-list");
    audList.innerHTML = profileData.target_audience.length ? profileData.target_audience.map(a => `<li>${escapeHtml(a.value)}</li>`).join("") : `<li style="color: var(--text-muted)">No specific audience statements found</li>`;

    // Use cases
    const ucList = document.getElementById("usecases-list");
    ucList.innerHTML = profileData.use_cases.length ? profileData.use_cases.map(u => `<li>${escapeHtml(u.value)}</li>`).join("") : `<li style="color: var(--text-muted)">No use cases detected</li>`;

    // Pricing
    const priceList = document.getElementById("pricing-list");
    if (profileData.pricing_information.length === 0) {
      priceList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No public pricing statements found on crawled pages.</div>`;
    } else {
      priceList.innerHTML = profileData.pricing_information.map(pr => {
        const ptxt = typeof pr.value === "object" ? (pr.value.price_text || `${pr.value.currency || '$'} ${pr.value.price}`) : pr.value;
        return `
          <div style="background: #0f172a; padding: 0.75rem 1rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
            <span>💰 <strong>${escapeHtml(ptxt)}</strong></span>
            <button class="btn btn-secondary btn-sm" onclick="openEvidenceModal('${pr.fact_id}')">Inspect Evidence</button>
          </div>
        `;
      }).join("");
    }

    // FAQs
    const faqList = document.getElementById("faqs-list");
    if (profileData.faqs.length === 0) {
      faqList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No FAQs detected in structured data or pages.</div>`;
    } else {
      faqList.innerHTML = profileData.faqs.map(f => {
        const q = typeof f.value === "object" ? f.value.question : "Q";
        const a = typeof f.value === "object" ? f.value.answer : f.value;
        return `
          <div style="background: #0f172a; padding: 0.75rem 1rem; border-radius: 6px;">
            <div style="font-weight: 600; color: var(--accent-info); font-size: 0.9rem; margin-bottom: 0.25rem;">Q: ${escapeHtml(q)}</div>
            <div style="color: var(--text-secondary); font-size: 0.85rem;">A: ${escapeHtml(a)}</div>
          </div>
        `;
      }).join("");
    }

    // Contact and Languages
    const contactDiv = document.getElementById("contact-info-content");
    const emails = profileData.contact_and_company_info.emails || [];
    const profiles = profileData.contact_and_company_info.social_profiles || [];
    const langs = profileData.supported_languages || [];
    contactDiv.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 0.4rem;">
        <div>📧 Emails: <strong>${emails.length ? emails.join(", ") : "None detected"}</strong></div>
        <div>🌐 Social Profiles: <strong>${profiles.length ? profiles.join(", ") : "None detected"}</strong></div>
        <div>🗣️ Supported Languages: <strong>${langs.length ? langs.join(", ") : "en"}</strong></div>
      </div>
    `;

  } catch (err) {
    console.error("Failed to load profile:", err);
  }
}

function renderFactsList() {
  if (!profileData || !profileData.facts) return;
  const container = document.getElementById("facts-container");
  const typeFilter = document.getElementById("fact-filter-type").value;
  const statusFilter = document.getElementById("fact-filter-status").value;

  let facts = profileData.facts;
  if (typeFilter) facts = facts.filter(f => f.fact_type === typeFilter);
  if (statusFilter === "confirmed") facts = facts.filter(f => f.user_confirmed === true);
  if (statusFilter === "unconfirmed") facts = facts.filter(f => f.user_confirmed === false);

  if (facts.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">No facts match the selected filter.</div>`;
    return;
  }

  container.innerHTML = facts.map(f => {
    const valStr = typeof f.fact_value === "object" ? JSON.stringify(f.fact_value, null, 2) : String(f.fact_value);
    const confirmedClass = f.user_confirmed ? "btn-success" : "btn-secondary";
    const confirmedText = f.user_confirmed ? "✓ Confirmed" : "Confirm Fact";

    return `
      <div class="fact-item" id="fact-card-${f.id}">
        <div class="fact-content">
          <div class="fact-type">${escapeHtml(f.fact_type)} &bull; ${Math.round(f.confidence * 100)}% Confidence</div>
          <div class="fact-val">${escapeHtml(valStr)}</div>
          <div class="fact-provenance">
            <strong>Source:</strong> ${f.source_url ? `<a href="${f.source_url}" target="_blank" style="color: var(--accent-primary);">${f.source_url}</a>` : 'Manual input'}
            ${f.evidence_snippet ? `<div style="margin-top: 0.25rem; font-style: italic;">"${escapeHtml(f.evidence_snippet.substring(0, 140))}..."</div>` : ''}
          </div>
        </div>
        <div class="fact-actions">
          <button class="btn btn-sm ${confirmedClass}" onclick="toggleConfirmFact('${f.id}', ${!f.user_confirmed})">${confirmedText}</button>
          <button class="btn btn-secondary btn-sm" onclick="openEvidenceModal('${f.id}')">Inspect</button>
          <button class="btn btn-sm" style="background: rgba(239, 68, 68, 0.2); color: #fca5a5;" onclick="deleteFact('${f.id}')">✕</button>
        </div>
      </div>
    `;
  }).join("");
}

async function toggleConfirmFact(factId, newStatus) {
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/facts/${factId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_confirmed: newStatus })
    });
    if (res.ok) {
      await loadBrandProfile(currentBrandId);
      renderFactsList();
    }
  } catch (e) {
    console.error("Toggle confirm failed:", e);
  }
}

async function deleteFact(factId) {
  if (!confirm("Remove this fact from the brand profile?")) return;
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/facts/${factId}`, {
      method: "DELETE"
    });
    if (res.ok) {
      await loadBrandProfile(currentBrandId);
      renderFactsList();
    }
  } catch (e) {
    console.error("Delete fact failed:", e);
  }
}

function openEvidenceModal(factId) {
  const fact = (profileData.facts || []).find(f => f.id === factId);
  if (!fact) return;

  document.getElementById("evidence-title").innerText = `Evidence for: ${fact.fact_type.toUpperCase()}`;
  const urlEl = document.getElementById("evidence-url");
  urlEl.innerText = fact.source_url || "Manual / Synthesized";
  urlEl.href = fact.source_url || "#";

  document.getElementById("evidence-method").innerText = `Method: ${fact.extraction_method} | Confidence: ${(fact.confidence * 100).toFixed(0)}%`;
  document.getElementById("evidence-snippet").innerText = fact.evidence_snippet || "No exact snippet recorded.";

  document.getElementById("evidence-modal").style.display = "flex";
}

function openAddFactModal() {
  document.getElementById("add-fact-modal").style.display = "flex";
}

function closeModal(id) {
  document.getElementById(id).style.display = "none";
}

async function handleCreateFact(e) {
  e.preventDefault();
  const ftype = document.getElementById("new-fact-type").value;
  const fval = document.getElementById("new-fact-val").value.trim();
  const fsnippet = document.getElementById("new-fact-snippet").value.trim();

  try {
    const res = await fetch(`/api/brands/${currentBrandId}/facts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fact_type: ftype,
        fact_value: fval,
        evidence_snippet: fsnippet || "Added manually during human verification",
        confidence: 1.0,
        user_confirmed: true
      })
    });
    if (res.ok) {
      closeModal("add-fact-modal");
      await loadBrandProfile(currentBrandId);
      renderFactsList();
    }
  } catch (err) {
    alert("Failed to add fact: " + err.message);
  }
}

async function loadCrawledPages(pageNumber = 1) {
  pagesCurrentPage = pageNumber;
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/pages?page=${pageNumber}&page_size=10`);
    if (!res.ok) return;
    const data = await res.json();

    const tbody = document.getElementById("pages-table-body");
    if (!data.items || data.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No crawled pages found.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.items.map(p => `
      <tr>
        <td><span class="badge ${p.http_status === 200 ? 'badge-completed' : 'badge-failed'}">HTTP ${p.http_status}</span></td>
        <td style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <a href="${p.final_url}" target="_blank" style="color: var(--accent-primary);">${p.final_url}</a>
        </td>
        <td><span class="badge" style="background: #1e293b; color: #94a3b8;">${escapeHtml(p.page_type)}</span></td>
        <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(p.title || 'Untitled')}</td>
        <td>${p.used_js ? '⚡ Yes' : 'No'}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="viewPageDetails('${p.id}')">View</button></td>
      </tr>
    `).join("");

    document.getElementById("pages-pagination-info").innerText = `Page ${data.page} of ${data.total_pages} (${data.total} total pages)`;
    document.getElementById("prev-page-btn").disabled = data.page <= 1;
    document.getElementById("next-page-btn").disabled = data.page >= data.total_pages;

  } catch (e) {
    console.error("Failed to load pages:", e);
  }
}

function changePagesPage(delta) {
  loadCrawledPages(pagesCurrentPage + delta);
}

async function viewPageDetails(pageId) {
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/pages/${pageId}`);
    if (!res.ok) return;
    const page = await res.json();

    document.getElementById("page-detail-title").innerText = page.title || "Crawled Page";
    document.getElementById("page-detail-url").innerText = page.final_url;
    document.getElementById("page-detail-status").innerText = `HTTP ${page.http_status}`;
    document.getElementById("page-detail-type").innerText = page.page_type.toUpperCase();
    document.getElementById("page-detail-desc").innerText = page.meta_description || "None";

    const headings = page.headings || {};
    const h1s = (headings.h1 || []).map(h => `H1: ${escapeHtml(h)}`).join("<br>");
    const h2s = (headings.h2 || []).map(h => `H2: ${escapeHtml(h)}`).join("<br>");
    document.getElementById("page-detail-headings").innerHTML = (h1s || h2s) ? `${h1s}<br>${h2s}` : "No major headings detected";

    document.getElementById("page-detail-text").innerText = page.extracted_text || "(No readable text)";
    document.getElementById("page-detail-modal").style.display = "flex";
  } catch (e) {
    console.error("View page details error:", e);
  }
}

async function triggerRefresh() {
  if (!confirm("Initiate a fresh crawl run for this brand? Your user-confirmed facts will be preserved.")) return;
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/profile-runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_limit: 30 })
    });
    if (res.ok) {
      const data = await res.json();
      currentRunId = data.run_id;
      switchTab("progress");
      startRunPolling(currentRunId);
    }
  } catch (e) {
    alert("Refresh failed: " + e.message);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
