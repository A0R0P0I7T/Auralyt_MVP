// ==========================================
// Authentication & Multi-Tenancy Management
// ==========================================
const AUTH_TOKEN_KEY = "auralyt_token";
let currentAuthUser = null;
let currentAuthOrg = null;
let authModalMode = "login"; // "login" or "register"

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

function clearAuthSession() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  currentAuthUser = null;
  currentAuthOrg = null;
  updateAuthHeaderUI();
}

function updateAuthHeaderUI() {
  const userBadge = document.getElementById("auth-user-badge");
  const logoutBtn = document.getElementById("auth-logout-btn");
  const loginBtn = document.getElementById("auth-login-btn");
  const orgNameEl = document.getElementById("auth-org-name");
  const userEmailEl = document.getElementById("auth-user-email");

  if (currentAuthUser && currentAuthOrg) {
    if (orgNameEl) orgNameEl.innerText = currentAuthOrg.name;
    if (userEmailEl) userEmailEl.innerText = currentAuthUser.email;
    if (userBadge) userBadge.style.display = "flex";
    if (logoutBtn) logoutBtn.style.display = "inline-block";
    if (loginBtn) loginBtn.style.display = "none";
  } else {
    if (userBadge) userBadge.style.display = "none";
    if (logoutBtn) logoutBtn.style.display = "none";
    if (loginBtn) loginBtn.style.display = "inline-block";
  }
}

function showAuthModal(mode = "login") {
  authModalMode = mode;
  const modal = document.getElementById("auth-modal");
  const title = document.getElementById("auth-modal-title");
  const subtitle = document.getElementById("auth-modal-subtitle");
  const nameGroup = document.getElementById("auth-name-group");
  const orgGroup = document.getElementById("auth-org-group");
  const submitBtn = document.getElementById("auth-submit-btn");
  const switchPrompt = document.getElementById("auth-switch-prompt");
  const switchBtn = document.getElementById("auth-switch-btn");
  const errorBox = document.getElementById("auth-modal-error");

  if (errorBox) errorBox.style.display = "none";

  if (mode === "register") {
    if (title) title.innerText = "Create Organization Account";
    if (subtitle) subtitle.innerText = "Register your organization to begin tracking AI visibility.";
    if (nameGroup) nameGroup.style.display = "block";
    if (orgGroup) orgGroup.style.display = "block";
    if (submitBtn) submitBtn.innerText = "Create Account & Sign In";
    if (switchPrompt) switchPrompt.innerText = "Already have an account?";
    if (switchBtn) switchBtn.innerText = "Sign in to existing account";
  } else {
    if (title) title.innerText = "Sign in to Auralyt";
    if (subtitle) subtitle.innerText = "Enter your credentials to access protected brand data and engines.";
    if (nameGroup) nameGroup.style.display = "none";
    if (orgGroup) orgGroup.style.display = "none";
    if (submitBtn) submitBtn.innerText = "Sign In";
    if (switchPrompt) switchPrompt.innerText = "Don't have an account?";
    if (switchBtn) switchBtn.innerText = "Create Organization Account";
  }

  if (modal) modal.style.display = "flex";
}

function hideAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.style.display = "none";
}

function toggleAuthMode() {
  showAuthModal(authModalMode === "login" ? "register" : "login");
}

function fillAdminCredentials() {
  const emailInput = document.getElementById("auth-email");
  const passInput = document.getElementById("auth-password");
  if (emailInput) emailInput.value = "admin@auralyt.ai";
  if (passInput) passInput.value = "AuralytAdmin2026!";
  if (authModalMode !== "login") showAuthModal("login");
}

async function checkAuthStatus() {
  const token = getAuthToken();
  if (!token) {
    updateAuthHeaderUI();
    return false;
  }
  try {
    const res = await _rawFetch("/api/auth/me", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (res.ok) {
      const data = await res.json();
      currentAuthUser = data.user;
      currentAuthOrg = data.active_organization || (data.organizations && data.organizations[0]);
      updateAuthHeaderUI();
      return true;
    } else {
      clearAuthSession();
      return false;
    }
  } catch (err) {
    console.error("Auth status verification error:", err);
    clearAuthSession();
    return false;
  }
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const errorBox = document.getElementById("auth-modal-error");
  if (errorBox) errorBox.style.display = "none";

  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;
  const fullName = document.getElementById("auth-full-name")?.value.trim() || "";
  const orgName = document.getElementById("auth-org-name-input")?.value.trim() || "";
  const submitBtn = document.getElementById("auth-submit-btn");

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = authModalMode === "register" ? "Registering..." : "Signing in...";
  }

  try {
    let endpoint = authModalMode === "register" ? "/api/auth/register" : "/api/auth/login";
    let body = authModalMode === "register"
      ? { email, password, full_name: fullName, organization_name: orgName }
      : { email, password };

    const res = await _rawFetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Authentication failed. Please verify credentials.");
    }

    setAuthToken(data.access_token);
    await checkAuthStatus();
    hideAuthModal();

    // Reload active brands and refresh dashboard
    await initBrandSelector();
  } catch (err) {
    if (errorBox) {
      errorBox.innerText = err.message || "Authentication error.";
      errorBox.style.display = "block";
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = authModalMode === "register" ? "Create Account & Sign In" : "Sign In";
    }
  }
}

async function handleLogout() {
  try {
    const token = getAuthToken();
    if (token) {
      await _rawFetch("/api/auth/logout", {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
    }
  } catch (e) {
    console.warn("Logout error:", e);
  } finally {
    clearAuthSession();
    currentBrandId = null;
    const select = document.getElementById("global-brand-select");
    if (select) select.innerHTML = '<option value="">Select Brand...</option>';
    showAuthModal("login");
  }
}

// Global Fetch Interceptor to inject Bearer token
const _rawFetch = window.fetch;
window.fetch = async function(resource, init = {}) {
  const token = getAuthToken();
  const url = typeof resource === "string" ? resource : (resource?.url || "");

  if (url.startsWith("/api") && !url.startsWith("/api/auth/login") && !url.startsWith("/api/auth/register")) {
    init = init || {};
    init.headers = init.headers || {};
    if (init.headers instanceof Headers) {
      if (token && !init.headers.has("Authorization")) {
        init.headers.set("Authorization", `Bearer ${token}`);
      }
    } else if (Array.isArray(init.headers)) {
      if (token && !init.headers.some(([k]) => k.toLowerCase() === "authorization")) {
        init.headers.push(["Authorization", `Bearer ${token}`]);
      }
    } else {
      if (token && !init.headers["Authorization"]) {
        init.headers["Authorization"] = `Bearer ${token}`;
      }
    }
  }

  const response = await _rawFetch(resource, init);

  if (response.status === 401 && url.startsWith("/api") && !url.startsWith("/api/auth/")) {
    console.warn("Unauthorized request to", url, ". Opening auth modal.");
    showAuthModal("login");
  }

  return response;
};

let currentBrandId = null;
let currentRunId = null;
let pollInterval = null;
let profileData = null;
let pagesCurrentPage = 1;
let promptsCurrentPage = 1;
let promptsTotalPages = 1;
let promptsSearchTimer = null;
let currentPromptsData = [];
let currentScanId = null;
let evalPollInterval = null;
let currentVisibilityResults = [];
let currentScansList = [];

function switchTab(tabName) {
  document.querySelectorAll(".tab-content").forEach(el => el.style.display = "none");
  document.querySelectorAll(".nav-btn").forEach(el => el.classList.remove("active"));

  const targetTab = document.getElementById(`tab-${tabName}`);
  if (targetTab) targetTab.style.display = "block";

  const btn = document.getElementById(`nav-${tabName}`) || Array.from(document.querySelectorAll(".nav-btn")).find(b => b.getAttribute("onclick")?.includes(tabName));
  if (btn) btn.classList.add("active");

  if (tabName === "experiment" && currentBrandId && currentScanId) {
    loadAndRenderExperimentResults(currentBrandId, currentScanId);
  }
  if (tabName === "profile" && currentBrandId) loadBrandProfile(currentBrandId);
  if (tabName === "facts" && currentBrandId) renderFactsList();
  if (tabName === "prompts" && currentBrandId) {
    loadPromptCoverage();
    loadPrompts(1);
  }
  if (tabName === "pages" && currentBrandId) loadCrawledPages(1);
  if (tabName === "evaluator" && currentBrandId) loadVisibilityData();
}

// ==========================================
// Minimal End-to-End Experiment Orchestration
// ==========================================

function updateExperimentStep(stepNum, status, detail) {
  const badge = document.getElementById(`exp-step-${stepNum}-status`);
  const detailEl = document.getElementById(`exp-step-${stepNum}-detail`);
  if (!badge) return;

  badge.innerText = status;
  if (status === "RUNNING") {
    badge.className = "badge badge-running";
  } else if (status === "COMPLETED") {
    badge.className = "badge badge-completed";
  } else if (status === "WARNING" || status === "LIMITATIONS") {
    badge.className = "badge badge-warning";
  } else if (status === "FAILED") {
    badge.className = "badge badge-failed";
  } else if (status === "BLOCKED" || status === "SKIPPED") {
    badge.className = "badge badge-pending";
  } else {
    badge.className = "badge";
  }

  if (detailEl && detail) {
    detailEl.innerText = detail;
  }
}

function updateExperimentProgress(pct, msg) {
  const bar = document.getElementById("exp-progress-bar");
  const msgEl = document.getElementById("exp-progress-msg");
  if (bar) bar.style.width = `${pct}%`;
  if (msgEl && msg) msgEl.innerText = msg;
}

async function handleRunExperiment(event) {
  if (event) event.preventDefault();

  const urlInput = document.getElementById("exp-website-url");
  const countInput = document.getElementById("exp-prompt-count");
  const providerInput = document.getElementById("exp-provider");
  const errorBox = document.getElementById("exp-error");
  const runBtn = document.getElementById("exp-run-btn");
  const progressCard = document.getElementById("exp-progress-card");
  const progressBadge = document.getElementById("exp-progress-badge");
  const resultsContainer = document.getElementById("exp-results-container");

  const websiteUrl = urlInput.value.trim();
  const promptCount = parseInt(countInput.value) || 20;
  const provider = providerInput.value || "gemini";

  errorBox.style.display = "none";
  errorBox.innerText = "";
  resultsContainer.style.display = "none";
  progressCard.style.display = "block";
  if (progressBadge) {
    progressBadge.className = "badge badge-running";
    progressBadge.innerText = "RUNNING";
  }
  runBtn.disabled = true;
  runBtn.innerText = "⏳ Running Pipeline...";

  // Reset Stepper
  updateExperimentStep(1, "RUNNING", "Crawling website & extracting ground truth facts...");
  updateExperimentStep(2, "WAITING", "Synthesize grounded buyer prompts");
  updateExperimentStep(3, "WAITING", "Query AI model & evaluate visibility");
  updateExperimentProgress(5, "Initiating Engine 1 website profiler...");

  const startTime = Date.now();
  const timer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const el = document.getElementById("exp-progress-elapsed");
    if (el) el.innerText = `${elapsed}s elapsed`;
  }, 1000);

  let activeStep = 1;

  try {
    // -----------------------------------------------------------------
    // STEP 1: Engine 1 (Website Profiling & Fact Extraction)
    // -----------------------------------------------------------------
    activeStep = 1;
    updateExperimentProgress(15, "Engine 1: Dispatching crawl request...");
    const onboardRes = await fetch("/api/brands/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        website_url: websiteUrl,
        page_limit: 10
      })
    });

    const onboardData = await onboardRes.json();
    if (!onboardRes.ok) {
      throw new Error(`Engine 1 initiation failed: ${onboardData.detail || "URL validation or crawl error"}`);
    }

    const brandId = onboardData.brand_id;
    const runId = onboardData.run_id;
    currentBrandId = brandId;
    currentRunId = runId;

    // Immediately synchronize active brand selector so the UI displays the brand being tested
    await initBrandSelector(brandId);

    // Poll profile run until completed or failed
    let e1Completed = false;
    let pollAttempts = 0;
    while (!e1Completed) {
      await new Promise(r => setTimeout(r, 1200));
      pollAttempts++;
      const runRes = await fetch(`/api/brands/profile-runs/${runId}`);
      if (!runRes.ok) continue;
      const runData = await runRes.json();

      const discovered = runData.pages_discovered || 0;
      const succeeded = runData.pages_succeeded || 0;
      updateExperimentStep(1, "RUNNING", `Pages: ${succeeded} succeeded / ${discovered} discovered`);
      const pct = Math.min(35, 15 + Math.floor(pollAttempts * 2));
      updateExperimentProgress(pct, `Engine 1: Crawling website (${succeeded} pages parsed)...`);

      if (runData.status === "completed" || runData.status === "completed_with_warnings") {
        e1Completed = true;
        if (runData.status === "completed_with_warnings" || (runData.warnings && runData.warnings.length > 0)) {
          const warnText = (runData.warnings && runData.warnings[0]) || "Completed with limitations";
          updateExperimentStep(1, "WARNING", `${succeeded} pages crawled (${warnText})`);
        } else {
          updateExperimentStep(1, "COMPLETED", `${succeeded} pages crawled & facts synthesized`);
        }
      } else if (runData.status === "failed") {
        throw new Error(`Engine 1 failed: ${runData.error_summary || "Crawl interrupted"}`);
      }
    }

    // -----------------------------------------------------------------
    // STEP 2: Engine 2 (Grounded Prompt Intelligence)
    // -----------------------------------------------------------------
    activeStep = 2;
    updateExperimentStep(2, "RUNNING", `Synthesizing ${promptCount} grounded prompts...`);
    updateExperimentProgress(45, `Engine 2: Generating ${promptCount} buyer prompts from profile facts...`);

    const genRes = await fetch(`/api/brands/${brandId}/prompts/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt_count: promptCount,
        force_regenerate: true
      })
    });

    const genData = await genRes.json();
    if (!genRes.ok) {
      throw new Error(`Engine 2 failed: ${genData.detail || "Could not generate grounded prompts"}`);
    }

    const generatedCount = genData.prompts_generated || promptCount;
    updateExperimentStep(2, "COMPLETED", `${generatedCount} grounded prompts generated & approved`);
    updateExperimentProgress(60, `Engine 2 complete (${generatedCount} prompts). Starting Engine 3...`);

    // -----------------------------------------------------------------
    // STEP 3: Engine 3 (AI Visibility Evaluation via Provider)
    // -----------------------------------------------------------------
    activeStep = 3;
    updateExperimentStep(3, "RUNNING", `Dispatching ${generatedCount} prompts to ${provider.toUpperCase()}...`);
    updateExperimentProgress(65, `Engine 3: Initiating visibility scan via ${provider}...`);

    const scanRes = await fetch(`/api/brands/${brandId}/visibility/scans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: provider,
        max_prompts: promptCount,
        force_rescan: true
      })
    });

    const scanData = await scanRes.json();
    if (!scanRes.ok) {
      throw new Error(`Engine 3 initiation failed: ${scanData.detail || "Scan dispatch error"}`);
    }

    const scanId = scanData.id;
    currentScanId = scanId;

    // Poll scan until completed or failed
    let e3Completed = false;
    let pollData = null;
    const pollStartTime = Date.now();
    const maxPollDurationMs = Math.max(180000, promptCount * 12000);

    while (!e3Completed) {
      if (Date.now() - pollStartTime > maxPollDurationMs) {
        throw new Error(`Engine 3 evaluation timed out after ${Math.round(maxPollDurationMs / 1000)} seconds.`);
      }

      await new Promise(r => setTimeout(r, 1500));
      const pollRes = await fetch(`/api/brands/${brandId}/visibility/scans/${scanId}`);
      if (!pollRes.ok) continue;
      pollData = await pollRes.json();

      const done = pollData.prompts_completed || 0;
      const failed = pollData.prompts_failed || 0;
      const total = pollData.prompts_selected || promptCount;
      const processed = done + failed;
      updateExperimentStep(3, "RUNNING", `Evaluating: ${processed} / ${total} prompts processed`);
      const pct = Math.min(95, 65 + Math.floor((processed / Math.max(1, total)) * 30));
      updateExperimentProgress(pct, `Engine 3: Querying ${provider} (${processed}/${total} processed)...`);

      if (pollData.status === "completed" || pollData.status === "completed_with_warnings" || pollData.status === "completed_with_errors") {
        e3Completed = true;
        const scoreStr = pollData.visibility_score != null ? `${Number(pollData.visibility_score).toFixed(1)}/100` : "N/A";
        if (pollData.status === "completed_with_errors" || failed > 0) {
          updateExperimentStep(3, "COMPLETED", `Score: ${scoreStr} (${done}/${total} succeeded, ${failed} failed)`);
        } else {
          updateExperimentStep(3, "COMPLETED", `Score: ${scoreStr}`);
        }
      } else if (pollData.status === "failed") {
        updateExperimentStep(3, "FAILED", pollData.error_summary || "Visibility evaluation failed");
        throw new Error(`Engine 3 failed: ${pollData.error_summary || "Visibility evaluation failed"}`);
      }
    }

    updateExperimentProgress(100, "Pipeline completed! Loading full visibility report...");
    clearInterval(timer);
    if (progressBadge) {
      if (pollData && pollData.status === "completed_with_errors") {
        progressBadge.className = "badge badge-warning";
        progressBadge.innerText = "COMPLETED (WITH ERRORS)";
      } else {
        progressBadge.className = "badge badge-completed";
        progressBadge.innerText = "COMPLETED";
      }
    }

    // -----------------------------------------------------------------
    // STEP 4: Render Complete Results
    // -----------------------------------------------------------------
    await loadAndRenderExperimentResults(brandId, scanId);

    // Save active experiment for refresh persistence
    localStorage.setItem("auralyt_active_experiment", JSON.stringify({ brand_id: brandId, scan_id: scanId }));
    const url = new URL(window.location);
    url.searchParams.set("brand_id", brandId);
    url.searchParams.set("scan_id", scanId);
    window.history.replaceState({}, "", url);

    await initBrandSelector(brandId);
  } catch (err) {
    console.error("Experiment pipeline error:", err);
    clearInterval(timer);

    if (progressBadge) {
      progressBadge.className = "badge badge-failed";
      progressBadge.innerText = "FAILED";
    }

    if (activeStep === 1) {
      updateExperimentStep(1, "FAILED", err.message || "Crawling and profiling failed");
      updateExperimentStep(2, "SKIPPED", "Skipped: Prerequisite Engine 1 profiling failed");
      updateExperimentStep(3, "SKIPPED", "Skipped: Prerequisite Engine 1 profiling failed");
    } else if (activeStep === 2) {
      updateExperimentStep(2, "FAILED", err.message || "Prompt generation failed");
      updateExperimentStep(3, "BLOCKED", "Blocked: Prerequisite Engine 2 failed (no approved prompts)");
    } else if (activeStep === 3) {
      updateExperimentStep(3, "FAILED", err.message || "Visibility evaluation failed");
    }

    let errorDetail = err.message || "An unexpected error occurred during pipeline execution.";
    if (errorDetail.includes("insufficient evidence")) {
      errorDetail += "\n\nActionable Recovery: The crawled pages did not provide enough grounded business context (missing category, products, or use cases). Provide brand metadata (business name, industry, and description) in the Brand Profile tab, or enter a website URL with accessible, indexable content.";
    } else if (errorDetail.includes("Authentication failed") || errorDetail.includes("API key not valid") || errorDetail.includes("UNAUTHENTICATED") || errorDetail.includes("All prompt queries failed")) {
      errorDetail += "\n\nActionable Recovery: The configured AI provider failed authentication (invalid or unauthenticated LLM_API_KEY). To evaluate offline without an external API key, switch the AI Provider dropdown to 'Offline Deterministic Mock', or update your environment with a valid Google Gemini API key.";
    }
    errorBox.innerText = errorDetail;
    errorBox.style.display = "block";
    updateExperimentProgress(0, "Pipeline interrupted due to an error.");
  } finally {
    runBtn.disabled = false;
    runBtn.innerText = "🚀 Run Experiment";
  }
}

async function loadAndRenderExperimentResults(brandId, scanId) {
  const container = document.getElementById("exp-results-container");
  const cardsContainer = document.getElementById("exp-results-cards");
  const countLabel = document.getElementById("exp-results-count-label");
  if (!container || !cardsContainer) return;

  try {
    const [scanRes, resultsRes, brandRes] = await Promise.all([
      fetch(`/api/brands/${brandId}/visibility/scans/${scanId}`),
      fetch(`/api/brands/${brandId}/visibility/scans/${scanId}/results`),
      fetch(`/api/brands/${brandId}`)
    ]);

    if (!scanRes.ok || !resultsRes.ok) {
      throw new Error("Failed to load experiment results from server.");
    }

    const scan = await scanRes.json();
    const resultsData = await resultsRes.json();
    const brand = brandRes.ok ? await brandRes.json() : { business_name: "Brand", domain: "" };

    const results = resultsData.results || resultsData.items || [];
    currentVisibilityResults = results;

    // 2. Populate Metrics Cards
    const scoreEl = document.getElementById("exp-score");
    const mentionEl = document.getElementById("exp-mention-rate");
    const recEl = document.getElementById("exp-recommend-rate");
    const promptsCountEl = document.getElementById("exp-prompts-count");

    if (scoreEl) scoreEl.innerText = scan.visibility_score != null ? `${Number(scan.visibility_score).toFixed(1)}` : "N/A";
    if (mentionEl) mentionEl.innerText = scan.mention_rate != null ? `${(Number(scan.mention_rate) * 100).toFixed(0)}%` : "N/A";
    if (recEl) recEl.innerText = scan.recommendation_rate != null ? `${(Number(scan.recommendation_rate) * 100).toFixed(0)}%` : "N/A";
    
    const completed = scan.prompts_completed != null ? scan.prompts_completed : results.length;
    const selected = scan.prompts_selected != null ? scan.prompts_selected : results.length;
    if (promptsCountEl) promptsCountEl.innerText = `${completed} / ${selected}`;

    // 3. Meta info banner
    const brandNameEl = document.getElementById("exp-brand-name");
    const brandDomainEl = document.getElementById("exp-brand-domain");
    const modelBadge = document.getElementById("exp-model-badge");
    const durationEl = document.getElementById("exp-duration");
    const tokensEl = document.getElementById("exp-total-tokens");

    if (brandNameEl) brandNameEl.innerText = brand.business_name || brand.domain;
    if (brandDomainEl) brandDomainEl.innerText = brand.domain;
    if (modelBadge) modelBadge.innerText = `${(scan.provider || "").toUpperCase()} (${scan.model_name || "default"})`;
    
    if (durationEl) {
      if (scan.duration_seconds != null) {
        durationEl.innerText = `${Number(scan.duration_seconds).toFixed(1)}s`;
      } else if (scan.completed_at && scan.started_at) {
        durationEl.innerText = `${((new Date(scan.completed_at) - new Date(scan.started_at)) / 1000).toFixed(1)}s`;
      } else {
        durationEl.innerText = "-";
      }
    }

    let totalTokens = 0;
    for (const r of results) {
      if (r.tokens_used) totalTokens += r.tokens_used;
    }
    if (tokensEl) tokensEl.innerText = totalTokens > 0 ? `${totalTokens.toLocaleString()} tokens` : (scan.tokens_consumed ? `${scan.tokens_consumed} tokens` : "N/A");

    if (countLabel) countLabel.innerText = `${results.length} Prompts Evaluated`;

    // 4. Render prompt evaluation cards
    if (results.length === 0) {
      cardsContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 2rem;">No prompt evaluations recorded for this scan.</div>`;
    } else {
      cardsContainer.innerHTML = results.map(r => {
        const isFailed = r.execution_status === "failed";

        let recBadge = "";
        if (isFailed) {
          recBadge = `<span class="badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px dashed rgba(148, 163, 184, 0.4);">UNEVALUATED</span>`;
        } else if (r.recommendation_status === "recommended") {
          recBadge = `<span class="badge" style="background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4);">RECOMMENDED</span>`;
        } else if (r.recommendation_status === "neutral_mention") {
          recBadge = `<span class="badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4);">NEUTRAL MENTION</span>`;
        } else if (r.recommendation_status === "not_recommended") {
          recBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);">NOT RECOMMENDED</span>`;
        } else {
          recBadge = `<span class="badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8;">NOT MENTIONED</span>`;
        }

        let mentionBadge = "";
        if (isFailed) {
          mentionBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);">QUERY FAILED</span>`;
        } else if (r.brand_mentioned) {
          mentionBadge = `<span class="badge badge-completed">MENTIONED</span>`;
        } else {
          mentionBadge = `<span class="badge badge-failed">NOT MENTIONED</span>`;
        }

        const pos = (!isFailed) ? (r.comparative_position || r.comparative_positioning) : null;
        const posChip = pos
          ? `<span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); text-transform: uppercase;">${escapeHtml(pos.replace(/_/g, ' '))}</span>`
          : "";

        const rank = (!isFailed) ? (r.visibility_rank || r.position_in_list) : null;
        const rankChip = rank
          ? `<span class="badge" style="background: #1e293b; color: #facc15; font-weight: 600;">Rank #${rank}</span>`
          : "";

        const latencyVal = r.latency_ms != null ? r.latency_ms : (r.execution_time_ms || 0);
        const tokensVal = r.tokens_used != null ? `${r.tokens_used} tok` : "";
        const statSnippet = `<span style="font-size: 0.75rem; color: var(--text-muted);">${latencyVal}ms ${tokensVal ? '• ' + tokensVal : ''}</span>`;

        const competitors = r.competitor_mentions || [];
        const compHtml = competitors.length > 0
          ? `<div style="display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center; margin-top: 0.5rem;">
               <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">Competitors Cited:</span>
               ${competitors.map(c => `<span style="background: #1e293b; border: 1px solid #334155; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; color: #f1f5f9;">${escapeHtml(c)}</span>`).join("")}
             </div>`
          : "";

        const providerCitations = r.provider_citations || [];
        const responseCitations = r.response_citations || (providerCitations.length === 0 ? (r.citations || []) : []);
        const renderCits = (label, list) => list.length > 0
          ? `<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-top: 0.5rem;">
               <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">${label}:</span>
               ${list.map(c => {
                 const url = typeof c === 'string' ? c : (c.url || '#');
                 const title = typeof c === 'string' ? c : (c.title || c.url);
                 return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="font-size: 0.75rem; color: var(--accent-primary); background: rgba(59, 130, 246, 0.1); padding: 0.15rem 0.5rem; border-radius: 4px; text-decoration: none; border: 1px solid rgba(59, 130, 246, 0.25);">${escapeHtml(title)}</a>`;
               }).join("")}
             </div>`
          : "";
        const citHtml = (providerCitations.length > 0 || responseCitations.length > 0)
          ? `${renderCits("Grounding Sources", providerCitations)}${renderCits("Cited Links", responseCitations)}`
          : "";

        const contextHtml = r.mention_context
          ? `<div style="background: #0f172a; border-left: 3px solid ${r.brand_mentioned ? 'var(--accent-success)' : 'var(--border-color)'}; padding: 0.6rem 0.85rem; border-radius: 0 6px 6px 0; font-size: 0.85rem; color: #cbd5e1; margin-top: 0.6rem; font-style: italic;">
               "${escapeHtml(r.mention_context)}"
             </div>`
          : "";

        const errorHtml = isFailed && r.error_details
          ? `<div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid #ef4444; padding: 0.5rem 0.85rem; border-radius: 0 4px 4px 0; font-size: 0.85rem; color: #fca5a5; margin-top: 0.6rem;">
               <strong>Query Error:</strong> ${escapeHtml(r.error_details)}
             </div>`
          : "";

        const promptId = r.prompt_id;
        const promptEvidenceBtn = promptId
          ? `<button class="btn btn-secondary btn-sm" onclick="openPromptEvidenceModal('${promptId}')" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">
               📋 Grounding Facts
             </button>`
          : "";

        return `
          <div class="card" style="margin-bottom: 1rem; padding: 1.25rem; background: #131c2e; border: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
              <div style="flex: 1; min-width: 250px;">
                <div style="font-size: 0.95rem; font-weight: 600; color: #f8fafc; line-height: 1.4;">
                  ${escapeHtml(r.prompt_text)}
                </div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-top: 0.5rem;">
                  ${mentionBadge}
                  ${recBadge}
                  ${posChip}
                  ${rankChip}
                  ${statSnippet}
                </div>
              </div>
              <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                ${promptEvidenceBtn}
                <button class="btn btn-secondary btn-sm" onclick="openRawResponseModal('${r.id}')" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">
                  🔍 Inspect Raw AI Response
                </button>
              </div>
            </div>

            ${errorHtml}
            ${contextHtml}
            ${compHtml}
            ${citHtml}
          </div>
        `;
      }).join("");
    }

    container.style.display = "block";
  } catch (err) {
    console.error("Error loading experiment results:", err);
  }
}

function viewBrandIntermediateProfile() {
  if (currentBrandId) {
    switchTab("profile");
  }
}

function viewBrandIntermediatePrompts() {
  if (currentBrandId) {
    switchTab("prompts");
  }
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
      prodList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No genuine products or services detected.</div>`;
    } else {
      prodList.innerHTML = profileData.products_and_services.map(p => {
        let name = "";
        let details = "";
        if (typeof p.value === "object" && p.value !== null) {
          name = p.value.name || p.value.title || "Product";
          const type = p.value.type ? `<span class="badge" style="background: #1e293b; font-size: 0.75rem; margin-left: 0.5rem;">${escapeHtml(p.value.type)}</span>` : "";
          const desc = p.value.description ? `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.2rem;">${escapeHtml(p.value.description)}</div>` : "";
          details = `${type}${desc}`;
        } else {
          name = String(p.value);
        }
        return `
          <div style="background: #0f172a; padding: 0.75rem 1rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-size: 0.95rem; font-weight: 500;">📦 ${escapeHtml(name)}</span>
              ${details}
            </div>
            <button class="btn btn-secondary btn-sm" onclick="openEvidenceModal('${p.fact_id}')">Inspect Source</button>
          </div>
        `;
      }).join("");
    }

    // Audiences
    const audList = document.getElementById("audience-list");
    audList.innerHTML = profileData.target_audience.length ? profileData.target_audience.map(a => `<li>${escapeHtml(typeof a.value === 'object' ? JSON.stringify(a.value) : a.value)}</li>`).join("") : `<li style="color: var(--text-muted)">No specific audience statements found</li>`;

    // Use cases
    const ucList = document.getElementById("usecases-list");
    ucList.innerHTML = profileData.use_cases.length ? profileData.use_cases.map(u => `<li>${escapeHtml(typeof u.value === 'object' ? JSON.stringify(u.value) : u.value)}</li>`).join("") : `<li style="color: var(--text-muted)">No use cases detected</li>`;

    // Pricing
    const priceList = document.getElementById("pricing-list");
    if (profileData.pricing_information.length === 0) {
      priceList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No verified public pricing found.</div>`;
    } else {
      priceList.innerHTML = profileData.pricing_information.map(pr => {
        let ptxt = "";
        if (typeof pr.value === "object" && pr.value !== null) {
          const v = pr.value;
          const currSym = v.currency_symbol || (v.currency === 'USD' ? '$' : (v.currency || '$'));
          const pType = v.pricing_type || (v.billing_basis === 'usage' ? 'usage_rate' : 'subscription_plan');
          const planName = v.plan_name || v.associated_product || 'Plan';

          if (pType === "free_tier" || v.billing_basis === "free" || (v.amount === 0 && !pType.includes("usage"))) {
            ptxt = `<strong>${escapeHtml(planName)}</strong>: Free ($0) <span style="color: var(--text-muted); font-size: 0.85rem;">(free tier)</span>`;
          } else if (pType === "custom" || v.billing_basis === "custom") {
            ptxt = `<strong>${escapeHtml(planName)}</strong>: <span style="color: var(--accent-info); font-size: 0.85rem;">Custom / Contact Sales</span>`;
          } else if (pType === "pay_as_you_go" || v.billing_basis === "pay_as_you_go") {
            const feeStr = v.currency === 'PERCENT' || v.currency_symbol === '%' ? `${v.amount}% fee` : `${currSym}${v.price}`;
            ptxt = `<strong>${escapeHtml(planName)}</strong>: Pay-as-you-go (${escapeHtml(feeStr)})`;
          } else if (pType === "setup_fee") {
            ptxt = `<strong>${escapeHtml(planName)}</strong>: ${currSym}${escapeHtml(String(v.price || v.amount))} <span style="color: var(--text-muted); font-size: 0.85rem;">(one-time setup fee)</span>`;
          } else if (pType === "usage_allowance" || (v.unit && v.unit.includes("allowance"))) {
            const numFormatted = Number(v.amount || v.price).toLocaleString();
            const prefixCurr = v.currency ? currSym : "";
            ptxt = `<strong>${escapeHtml(planName)}</strong>: ${prefixCurr}${escapeHtml(numFormatted)} <span style="color: var(--accent-info); font-size: 0.85rem;">(${escapeHtml(v.unit || 'allowance')})</span>`;
          } else if (pType === "usage_rate" || v.billing_basis === "usage") {
            const unitLabel = v.unit || 'unit';
            ptxt = `<strong>${escapeHtml(planName)}</strong>: ${currSym}${escapeHtml(String(v.price || v.amount))} / ${escapeHtml(unitLabel)} <span style="color: var(--text-muted); font-size: 0.85rem;">(usage)</span>`;
          } else if (pType === "unverified" || v.billing_basis === "unspecified") {
            ptxt = `<strong>${escapeHtml(planName)}</strong>: <span style="color: var(--text-muted); font-size: 0.85rem;">Price unverified (${escapeHtml(v.price_text || 'contact provider')})</span>`;
          } else if (v.formatted_display) {
            ptxt = `<span>${escapeHtml(v.formatted_display)}</span>`;
          } else {
            const price = `${currSym}${v.price || v.amount}`;
            const basis = v.billing_basis && v.billing_basis !== 'unspecified' ? ` <span style="color: var(--text-muted); font-size: 0.85rem;">(${escapeHtml(v.billing_basis)})</span>` : "";
            ptxt = `<strong>${escapeHtml(planName)}</strong>: <span>${escapeHtml(price)}</span>${basis}`;
          }
          const features = v.features && v.features.length ? `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.2rem;">Features: ${escapeHtml(v.features.slice(0, 3).join(", "))}</div>` : "";
          ptxt = `<div>${ptxt}${features}</div>`;
        } else {
          ptxt = `<span>${escapeHtml(String(pr.value))}</span>`;
        }
        return `
          <div style="background: #0f172a; padding: 0.75rem 1rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
            <div>💰 ${ptxt}</div>
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
  if (statusFilter === "confirmed") facts = facts.filter(f => f.user_confirmed === true && !f.is_rejected);
  if (statusFilter === "unconfirmed") facts = facts.filter(f => !f.user_confirmed && !f.is_rejected);
  if (statusFilter === "rejected") facts = facts.filter(f => f.is_rejected === true);

  if (facts.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">No facts match the selected filter.</div>`;
    return;
  }

  container.innerHTML = facts.map(f => {
    const valStr = typeof f.fact_value === "object" ? JSON.stringify(f.fact_value, null, 2) : String(f.fact_value);
    let statusPill = "";
    if (f.is_rejected) {
      statusPill = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4);">✕ Rejected</span>`;
    } else if (f.user_confirmed) {
      statusPill = `<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.4);">✓ Confirmed</span>`;
    } else {
      statusPill = `<span class="badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.4);">⏳ Pending Review</span>`;
    }

    return `
      <div class="fact-item" id="fact-card-${f.id}">
        <div class="fact-content">
          <div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.35rem;">
            <div class="fact-type">${escapeHtml(f.fact_type)} &bull; ${Math.round(f.confidence * 100)}% Confidence</div>
            ${statusPill}
          </div>
          <div class="fact-val">${escapeHtml(valStr)}</div>
          <div class="fact-provenance">
            <strong>Source:</strong> ${f.source_url ? `<a href="${f.source_url}" target="_blank" style="color: var(--accent-primary);">${f.source_url}</a>` : 'Manual input'}
            ${f.evidence_snippet ? `<div style="margin-top: 0.25rem; font-style: italic;">"${escapeHtml(f.evidence_snippet.substring(0, 140))}..."</div>` : ''}
          </div>
        </div>
        <div class="fact-actions">
          ${!f.user_confirmed ? `<button class="btn btn-sm btn-success" onclick="toggleConfirmFact('${f.id}', true)">✓ Confirm</button>` : `<button class="btn btn-sm btn-secondary" onclick="toggleConfirmFact('${f.id}', false)">Unconfirm</button>`}
          ${!f.is_rejected ? `<button class="btn btn-sm" style="background: rgba(239, 68, 68, 0.2); color: #fca5a5;" onclick="toggleRejectFact('${f.id}', true)">✕ Reject</button>` : `<button class="btn btn-sm btn-secondary" onclick="toggleRejectFact('${f.id}', false)">↺ Restore</button>`}
          <button class="btn btn-secondary btn-sm" onclick="openEvidenceModal('${f.id}')">Inspect</button>
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
      body: JSON.stringify({ user_confirmed: newStatus, is_rejected: false })
    });
    if (res.ok) {
      await loadBrandProfile(currentBrandId);
      renderFactsList();
    }
  } catch (e) {
    console.error("Toggle confirm failed:", e);
  }
}

async function toggleRejectFact(factId, isRejected) {
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/facts/${factId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_rejected: isRejected, user_confirmed: false })
    });
    if (res.ok) {
      await loadBrandProfile(currentBrandId);
      renderFactsList();
    }
  } catch (e) {
    console.error("Toggle reject failed:", e);
  }
}

async function deleteFact(factId) {
  if (!confirm("Permanently delete this fact from the brand profile?")) return;
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

    // Render crawl diagnostics if available
    const diagBox = document.getElementById("crawl-budget-diagnostics");
    if (profileData && (profileData.crawl_summary || (profileData.active_run && profileData.active_run.crawl_summary))) {
      const summary = profileData.crawl_summary || profileData.active_run.crawl_summary;
      diagBox.style.display = "block";
      document.getElementById("crawl-budget-run-status").innerText = (summary.run_status || "COMPLETED").toUpperCase();
      document.getElementById("crawl-budget-run-status").className = `badge badge-${(summary.run_status || 'completed').replace('_with_warnings', '')}`;

      const metricsDiv = document.getElementById("crawl-budget-metrics");
      metricsDiv.innerHTML = `
        <div>Discovered: <strong>${summary.pages_discovered || 0}</strong></div>
        <div>Attempted: <strong>${summary.pages_attempted || 0}</strong></div>
        <div>Succeeded: <strong style="color: var(--accent-success);">${summary.pages_succeeded || 0}</strong></div>
        <div>Skipped: <strong style="color: #fbbf24;">${summary.pages_skipped || 0}</strong></div>
        <div>Failed: <strong style="color: var(--accent-danger);">${summary.pages_failed || 0}</strong></div>
        <div>Bytes: <strong>${((summary.aggregate_bytes_processed || 0) / (1024 * 1024)).toFixed(2)} MB</strong></div>
      `;

      const skipsDiv = document.getElementById("crawl-skip-reasons");
      const reasons = summary.skip_reasons || {};
      const reasonEntries = Object.entries(reasons).filter(([k, v]) => v > 0);
      if (reasonEntries.length > 0) {
        skipsDiv.innerHTML = `<strong>Skip Reasons:</strong> ` + reasonEntries.map(([k, v]) => `${k.replace(/_/g, ' ')} (${v})`).join(" &bull; ");
      } else {
        skipsDiv.innerHTML = "";
      }
    }

    const tbody = document.getElementById("pages-table-body");
    if (!data.items || data.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No crawled pages found.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.items.map(p => `
      <tr>
        <td><span class="badge ${p.http_status === 200 ? 'badge-completed' : 'badge-failed'}">HTTP ${p.http_status}</span></td>
        <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <a href="${p.final_url}" target="_blank" style="color: var(--accent-primary);">${p.final_url}</a>
        </td>
        <td><span class="badge" style="background: #1e293b; color: #94a3b8;">${escapeHtml(p.page_type)}</span></td>
        <td><span class="badge" style="background: ${p.facts_count > 0 ? '#065f46' : '#334155'}; color: #e2e8f0;">${p.facts_count} facts</span></td>
        <td style="max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(p.title || 'Untitled')}</td>
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

    const factsList = page.extracted_facts || [];
    document.getElementById("page-detail-facts-count").innerText = factsList.length;
    const factsContainer = document.getElementById("page-detail-facts-list");
    if (factsList.length === 0) {
      factsContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">This page contributed 0 facts to the brand profile.</div>`;
    } else {
      factsContainer.innerHTML = factsList.map(f => {
        const valStr = typeof f.fact_value === 'object' ? JSON.stringify(f.fact_value) : String(f.fact_value);
        return `
          <div style="padding: 0.35rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span class="badge" style="background: #334155; font-size: 0.75rem;">${escapeHtml(f.fact_type)}</span>
              <span style="font-size: 0.85rem; margin-left: 0.5rem; color: #f8fafc;">${escapeHtml(valStr)}</span>
            </div>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${Math.round(f.confidence * 100)}%</span>
          </div>
        `;
      }).join("");
    }

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

/* ==========================================================
   ENGINE 2: PROMPT INTELLIGENCE FUNCTIONS
   ========================================================== */

async function handleGeneratePrompts() {
  if (!currentBrandId) {
    alert("Please select or onboard a brand first.");
    return;
  }

  const errorBanner = document.getElementById("prompts-error-banner");
  errorBanner.style.display = "none";

  const btn = document.getElementById("generate-prompts-btn");
  const countSelect = document.getElementById("prompt_count_select");
  const langInput = document.getElementById("prompt_lang_override");
  const forceCheckbox = document.getElementById("prompt_force_regen");

  const promptCount = parseInt(countSelect.value) || 20;
  const langOverride = langInput.value.trim() || null;
  const forceRegen = forceCheckbox.checked;

  btn.disabled = true;
  btn.innerText = "Generating Prompts...";

  try {
    const res = await fetch(`/api/brands/${currentBrandId}/prompts/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt_count: promptCount,
        language: langOverride,
        force_regenerate: forceRegen
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to generate evaluation prompts.");
    }

    // Display run status
    const badge = document.getElementById("prompt-run-status-badge");
    if (badge) {
      badge.style.display = "inline-block";
      badge.innerText = (data.status || "COMPLETED").toUpperCase();
      badge.className = `badge badge-${data.status === "completed" ? "completed" : "pending"}`;
    }

    const runInfoBox = document.getElementById("prompts-run-info");
    if (runInfoBox) runInfoBox.style.display = "block";
    const runId = (data.run_id || data.id || "");
    const runIdEl = document.getElementById("info-run-id");
    if (runIdEl) runIdEl.innerText = runId ? runId.substring(0, 8) : "";
    const provEl = document.getElementById("info-provider");
    if (provEl) provEl.innerText = data.provider || "rule-based";
    const profEl = document.getElementById("info-profile-ver");
    if (profEl) profEl.innerText = `v${data.profile_version || 1}`;
    const countEl = document.getElementById("info-count");
    if (countEl) countEl.innerText = data.prompts_generated != null ? data.prompts_generated : 0;
    const durEl = document.getElementById("info-duration");
    if (durEl) durEl.innerText = data.duration_seconds || "0.0";

    // Reload coverage and prompts
    await loadPromptCoverage();
    await loadPrompts(1);

  } catch (err) {
    errorBanner.innerText = err.message;
    errorBanner.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.innerText = "⚡ Generate Prompts";
  }
}

async function loadPromptCoverage() {
  if (!currentBrandId) return;
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/prompts/coverage`);
    if (!res.ok) return;
    const cov = await res.json();

    document.getElementById("cov-total-prompts").innerText = cov.total_prompts || 0;
    document.getElementById("cov-approved-prompts").innerText = cov.approved_prompts || 0;
    document.getElementById("cov-avg-score").innerText = (cov.average_quality_score || 0).toFixed(2);

    const categories = Object.keys(cov.by_category || {});
    document.getElementById("cov-categories-count").innerText = categories.length;

    const chipsContainer = document.getElementById("category-chips-list");
    if (categories.length === 0) {
      chipsContainer.innerHTML = `<span class="category-chip">No prompts generated yet</span>`;
    } else {
      chipsContainer.innerHTML = categories.map(cat => {
        const count = cov.by_category[cat];
        return `
          <span class="category-chip active" style="cursor: pointer;" onclick="filterCategoryFromChip('${cat}')">
            <strong>${escapeHtml(formatCategoryName(cat))}</strong> (${count})
          </span>
        `;
      }).join("");
    }
  } catch (e) {
    console.error("Failed to load prompt coverage:", e);
  }
}

function filterCategoryFromChip(cat) {
  const catSelect = document.getElementById("filter-prompt-category");
  catSelect.value = cat;
  loadPrompts(1);
}

function formatCategoryName(cat) {
  return cat.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

async function loadPrompts(page = 1) {
  if (!currentBrandId) return;
  promptsCurrentPage = page;

  const cat = document.getElementById("filter-prompt-category").value;
  const stage = document.getElementById("filter-prompt-stage").value;
  const approved = document.getElementById("filter-prompt-approved").value;
  const search = document.getElementById("filter-prompt-search").value.trim();

  let url = `/api/brands/${currentBrandId}/prompts?page=${page}&page_size=15`;
  if (cat) url += `&category=${encodeURIComponent(cat)}`;
  if (stage) url += `&buying_stage=${encodeURIComponent(stage)}`;
  if (approved !== "") url += `&is_approved=${encodeURIComponent(approved)}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;

  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    currentPromptsData = data.items;
    promptsTotalPages = data.total_pages || 1;

    renderPromptsTable(data.items);

    document.getElementById("prompts-list-count-label").innerText = `Showing ${data.items.length} of ${data.total} prompts`;
    document.getElementById("prompts-pagination-info").innerText = `Page ${data.page} of ${data.total_pages || 1} (${data.total} total)`;
    document.getElementById("prev-prompts-btn").disabled = data.page <= 1;
    document.getElementById("next-prompts-btn").disabled = data.page >= data.total_pages;

  } catch (e) {
    console.error("Failed to load prompts:", e);
  }
}

function renderPromptsTable(items) {
  const tbody = document.getElementById("prompts-table-body");
  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No matching prompts found.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(p => {
    const scoreVal = p.quality_score || 0;
    let scoreClass = "score-low";
    if (scoreVal >= 0.8) scoreClass = "score-high";
    else if (scoreVal >= 0.6) scoreClass = "score-mid";

    const isApproved = p.is_approved;
    let statusPill = "";
    if (p.is_archived) {
      statusPill = `<span class="badge" style="background: rgba(239,68,68,0.2); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4);">Archived / Rejected</span>`;
    } else if (isApproved) {
      statusPill = `<span class="badge" style="background: rgba(16,185,129,0.2); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.4);">Approved</span>`;
    } else {
      statusPill = `<span class="badge" style="background: rgba(245,158,11,0.2); color: #fcd34d; border: 1px solid rgba(245,158,11,0.4);">Pending Review</span>`;
    }

    const editedPill = p.user_edited ? `<span class="badge-edited">EDITED</span>` : "";

    return `
      <tr style="${p.is_archived ? 'opacity: 0.5;' : ''}">
        <td>
          <div class="prompt-text-cell">
            ${escapeHtml(p.text)} ${editedPill}
          </div>
        </td>
        <td>
          <span class="badge" style="background: #334155; color: #f8fafc; font-size: 0.75rem;">
            ${escapeHtml(formatCategoryName(p.category))}
          </span>
        </td>
        <td>
          <div style="display: flex; flex-direction: column; gap: 0.25rem;">
            <span class="badge badge-stage">${escapeHtml(p.buying_stage)}</span>
            <span class="badge badge-intent">${escapeHtml(p.intent)}</span>
          </div>
        </td>
        <td>
          <span class="score-badge ${scoreClass}">★ ${(scoreVal).toFixed(2)}</span>
        </td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openPromptEvidenceModal('${p.id}')">
            Grounding (${p.provenance_fact_ids.length})
          </button>
        </td>
        <td>
          ${statusPill}
        </td>
        <td>
          <div style="display: flex; gap: 0.35rem; align-items: center;">
            <button class="btn btn-sm ${isApproved ? 'btn-secondary' : 'btn-success'}" onclick="togglePromptApproval('${p.id}', ${isApproved})" title="${isApproved ? 'Unapprove' : 'Approve'}">
              ${isApproved ? '✓' : 'Approve'}
            </button>
            <button class="btn btn-secondary btn-sm" onclick="openEditPromptModal('${p.id}')" title="Edit">
              ✎
            </button>
            <button class="btn btn-secondary btn-sm" onclick="archivePrompt('${p.id}')" title="Archive" style="color: var(--accent-danger);">
              ✕
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function debouncePromptsSearch() {
  if (promptsSearchTimer) clearTimeout(promptsSearchTimer);
  promptsSearchTimer = setTimeout(() => {
    loadPrompts(1);
  }, 300);
}

function changePromptsPage(delta) {
  loadPrompts(promptsCurrentPage + delta);
}

async function togglePromptApproval(promptId, currentStatus) {
  try {
    const res = await fetch(`/api/prompts/${promptId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_approved: !currentStatus })
    });
    if (res.ok) {
      loadPromptCoverage();
      loadPrompts(promptsCurrentPage);
    }
  } catch (e) {
    alert("Approval update failed: " + e.message);
  }
}

async function archivePrompt(promptId) {
  if (!confirm("Archive this prompt? It will be excluded from evaluation sets.")) return;
  try {
    const res = await fetch(`/api/prompts/${promptId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_archived: true })
    });
    if (res.ok) {
      loadPromptCoverage();
      loadPrompts(promptsCurrentPage);
    }
  } catch (e) {
    alert("Archive failed: " + e.message);
  }
}

async function openEditPromptModal(promptId) {
  try {
    const res = await fetch(`/api/prompts/${promptId}`);
    if (!res.ok) return;
    const p = await res.json();

    document.getElementById("edit-prompt-id").value = p.id;
    document.getElementById("edit-prompt-text").value = p.text;
    document.getElementById("edit-prompt-approved").checked = p.is_approved;
    document.getElementById("edit-prompt-archived").checked = p.is_archived;

    document.getElementById("edit-prompt-modal").style.display = "flex";
  } catch (e) {
    console.error("Open edit prompt error:", e);
  }
}

async function handleSavePromptEdit(event) {
  event.preventDefault();
  const promptId = document.getElementById("edit-prompt-id").value;
  const newText = document.getElementById("edit-prompt-text").value.trim();
  const isApproved = document.getElementById("edit-prompt-approved").checked;
  const isArchived = document.getElementById("edit-prompt-archived").checked;

  try {
    const res = await fetch(`/api/prompts/${promptId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: newText,
        is_approved: isApproved,
        is_archived: isArchived
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to update prompt.");
    }

    closeModal("edit-prompt-modal");
    loadPromptCoverage();
    loadPrompts(promptsCurrentPage);
  } catch (e) {
    alert(e.message);
  }
}

async function openPromptEvidenceModal(promptId) {
  try {
    const res = await fetch(`/api/prompts/${promptId}`);
    if (!res.ok) return;
    const p = await res.json();

    document.getElementById("pe-prompt-text").innerText = p.text;
    document.getElementById("pe-category").innerText = formatCategoryName(p.category);
    document.getElementById("pe-stage").innerText = `Stage: ${p.buying_stage.toUpperCase()}`;
    document.getElementById("pe-intent").innerText = `Intent: ${p.intent.toUpperCase()}`;
    document.getElementById("pe-score").innerText = `Score: ${(p.quality_score || 0).toFixed(2)}`;

    // Scores breakdown
    const scores = p.scores || {};
    const scoresGrid = document.getElementById("pe-scores-grid");
    scoresGrid.innerHTML = Object.entries(scores).map(([k, v]) => `
      <div style="background: #0f172a; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--border-color);">
        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: capitalize;">${k.replace(/_/g, ' ')}</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: #93c5fd;">${typeof v === 'number' ? v.toFixed(2) : v}</div>
      </div>
    `).join("");

    // Grounded evidence snippets
    const evidenceList = document.getElementById("pe-evidence-list");
    const evidence = p.grounding_evidence || [];
    if (evidence.length === 0) {
      evidenceList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">No direct text snippet linked. Grounded via verified category facts.</div>`;
    } else {
      evidenceList.innerHTML = evidence.map(ev => `
        <div style="background: #0f172a; border-left: 3px solid var(--accent-primary); padding: 0.6rem 0.85rem; border-radius: 0 6px 6px 0; font-size: 0.85rem; color: #cbd5e1;">
          "${escapeHtml(ev)}"
        </div>
      `).join("");
    }

    document.getElementById("prompt-evidence-modal").style.display = "flex";
  } catch (e) {
    console.error("Open prompt evidence error:", e);
  }
}

/* ==========================================================
   ENGINE 3: AI VISIBILITY EVALUATOR FUNCTIONS
   ========================================================== */

async function loadVisibilityData(targetScanId = null) {
  if (!currentBrandId) {
    document.getElementById("eval-results-container").innerHTML = `
      <div style="text-align: center; color: var(--text-muted); padding: 2rem;">
        Please select or onboard a brand first.
      </div>
    `;
    return;
  }

  const errorBanner = document.getElementById("eval-error-banner");
  errorBanner.style.display = "none";

  try {
    const res = await fetch(`/api/brands/${currentBrandId}/visibility/scans`);
    if (!res.ok) {
      throw new Error("Failed to load visibility scans.");
    }
    const data = await res.json();
    const scans = data.items || [];
    currentScansList = scans;

    const historySelect = document.getElementById("eval_history_scan_select");

    if (scans.length === 0) {
      resetVisibilityScorecard();
      if (historySelect) {
        historySelect.style.display = "none";
        historySelect.innerHTML = "";
      }
      document.getElementById("eval-results-container").innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No visibility scans recorded yet. Select options above and run your first scan.
        </div>
      `;
      return;
    }

    // Determine target scan: either requested, or currentScanId if in list, or latest
    let activeScan = scans[0];
    if (targetScanId) {
      const match = scans.find(s => s.id === targetScanId);
      if (match) activeScan = match;
    } else if (currentScanId) {
      const match = scans.find(s => s.id === currentScanId);
      if (match) activeScan = match;
    }

    currentScanId = activeScan.id;

    if (historySelect) {
      historySelect.style.display = "inline-block";
      historySelect.innerHTML = scans.map(s => {
        const dt = new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const score = s.visibility_score != null ? `${Number(s.visibility_score).toFixed(1)}/100` : s.status;
        return `<option value="${s.id}" ${s.id === activeScan.id ? 'selected' : ''}>Scan ${s.id.slice(0, 8)} (v${s.profile_version}, ${s.provider}, ${score}) - ${dt}</option>`;
      }).join("");
    }

    updateScanSummaryUI(activeScan);

    if (activeScan.status === "pending" || activeScan.status === "running") {
      startScanPolling(activeScan.id);
    } else {
      if (evalPollInterval) {
        clearInterval(evalPollInterval);
        evalPollInterval = null;
      }
      const btn = document.getElementById("start-eval-btn");
      if (btn) {
        btn.disabled = false;
        btn.innerText = "🚀 Run AI Visibility Scan";
      }
      await loadScanResults(activeScan.id);
    }
  } catch (err) {
    console.error("Error loading visibility data:", err);
    errorBanner.innerText = err.message;
    errorBanner.style.display = "block";
  }
}

async function handleSelectHistoricalScan(selectedScanId) {
  if (!selectedScanId) return;
  await loadVisibilityData(selectedScanId);
}

function resetVisibilityScorecard() {
  document.getElementById("eval-status-badge").innerText = "READY";
  document.getElementById("eval-status-badge").className = "badge badge-pending";
  document.getElementById("stat-visibility-score").innerText = "N/A";
  document.getElementById("stat-mention-rate").innerText = "N/A";
  document.getElementById("stat-recommendation-rate").innerText = "N/A";
  document.getElementById("stat-avg-position").innerText = "N/A";
  document.getElementById("stat-eval-completed").innerText = "0 / 0";
  document.getElementById("eval-run-info").style.display = "none";
  const mockBanner = document.getElementById("eval-mock-banner");
  if (mockBanner) mockBanner.style.display = "none";
}

async function handleStartVisibilityScan() {
  if (!currentBrandId) {
    alert("Please select or onboard a brand first.");
    return;
  }

  const errorBanner = document.getElementById("eval-error-banner");
  errorBanner.style.display = "none";

  const btn = document.getElementById("start-eval-btn");
  const provider = document.getElementById("eval_provider_select").value;
  const maxPrompts = parseInt(document.getElementById("eval_max_prompts").value) || 20;
  const forceRescan = document.getElementById("eval_force_rescan").checked;

  btn.disabled = true;
  btn.innerText = "⏳ Initiating Visibility Scan...";

  try {
    const res = await fetch(`/api/brands/${currentBrandId}/visibility/scans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: provider,
        max_prompts: maxPrompts,
        force_rescan: forceRescan
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to start visibility scan.");
    }

    currentScanId = data.id;
    updateScanSummaryUI(data);

    btn.innerText = "⚡ Evaluating Prompts...";
    startScanPolling(data.id);
  } catch (err) {
    errorBanner.innerText = err.message;
    errorBanner.style.display = "block";
    btn.disabled = false;
    btn.innerText = "🚀 Run AI Visibility Scan";
  }
}

function startScanPolling(scanId) {
  if (evalPollInterval) clearInterval(evalPollInterval);

  const btn = document.getElementById("start-eval-btn");
  if (btn) {
    btn.disabled = true;
    btn.innerText = "⚡ Evaluating Prompts...";
  }

  const pollStartTime = Date.now();
  const checkStatus = async () => {
    try {
      if (Date.now() - pollStartTime > 180000) {
        clearInterval(evalPollInterval);
        evalPollInterval = null;
        if (btn) {
          btn.disabled = false;
          btn.innerText = "🚀 Run AI Visibility Scan";
        }
        const errorBanner = document.getElementById("eval-error-banner");
        if (errorBanner) {
          errorBanner.innerText = "Visibility scan polling timed out after 180s. Refresh page to view updated status.";
          errorBanner.style.display = "block";
        }
        return;
      }

      const res = await fetch(`/api/brands/${currentBrandId}/visibility/scans/${scanId}`);
      if (!res.ok) return;
      const scan = await res.json();

      updateScanSummaryUI(scan);

      if (scan.status === "completed" || scan.status === "completed_with_warnings" || scan.status === "completed_with_errors" || scan.status === "failed") {
        clearInterval(evalPollInterval);
        evalPollInterval = null;

        if (btn) {
          btn.disabled = false;
          btn.innerText = "🚀 Run AI Visibility Scan";
        }

        const errorBanner = document.getElementById("eval-error-banner");
        if (scan.status === "failed") {
          if (errorBanner) {
            errorBanner.innerText = scan.error_summary || "Visibility scan failed.";
            errorBanner.style.display = "block";
          }
        } else {
          if (scan.status === "completed_with_errors" && errorBanner) {
            errorBanner.innerText = `Scan completed with partial errors: ${scan.error_summary || "Some prompts failed to evaluate."}`;
            errorBanner.style.display = "block";
          } else if (errorBanner) {
            errorBanner.style.display = "none";
          }
          await loadScanResults(scan.id);
        }

        // Refresh scan history selector with updated score & status
        const historyRes = await fetch(`/api/brands/${currentBrandId}/visibility/scans`);
        if (historyRes.ok) {
          const histData = await historyRes.json();
          const scans = histData.items || [];
          currentScansList = scans;
          const historySelect = document.getElementById("eval_history_scan_select");
          if (historySelect && scans.length > 0) {
            historySelect.style.display = "inline-block";
            historySelect.innerHTML = scans.map(s => {
              const dt = new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              const score = s.visibility_score != null ? `${Number(s.visibility_score).toFixed(1)}/100` : s.status;
              return `<option value="${s.id}" ${s.id === scan.id ? 'selected' : ''}>Scan ${s.id.slice(0, 8)} (v${s.profile_version}, ${s.provider}, ${score}) - ${dt}</option>`;
            }).join("");
          }
        }
      }
    } catch (e) {
      console.error("Scan poll error:", e);
    }
  };

  checkStatus();
  evalPollInterval = setInterval(checkStatus, 1500);
}

function updateScanSummaryUI(scan) {
  const badge = document.getElementById("eval-status-badge");
  badge.innerText = (scan.status || "READY").toUpperCase().replace(/_/g, ' ');
  let badgeClass = "badge-pending";
  if (scan.status === "completed") badgeClass = "badge-completed";
  else if (scan.status === "completed_with_warnings" || scan.status === "completed_with_errors") badgeClass = "badge-warning";
  else if (scan.status === "failed") badgeClass = "badge-failed";
  badge.className = `badge ${badgeClass}`;

  const mockBanner = document.getElementById("eval-mock-banner");
  if (mockBanner) {
    mockBanner.style.display = (scan.provider === "mock") ? "block" : "none";
  }

  document.getElementById("stat-visibility-score").innerText = scan.visibility_score != null ? Number(scan.visibility_score).toFixed(1) : "N/A";
  document.getElementById("stat-mention-rate").innerText = scan.mention_rate != null ? `${(Number(scan.mention_rate) * 100).toFixed(0)}%` : "N/A";
  document.getElementById("stat-recommendation-rate").innerText = scan.recommendation_rate != null ? `${(Number(scan.recommendation_rate) * 100).toFixed(0)}%` : "N/A";
  
  const avgPos = scan.average_position;
  document.getElementById("stat-avg-position").innerText = avgPos ? `#${avgPos.toFixed(1)}` : "N/A";

  const completed = scan.prompts_completed != null ? scan.prompts_completed : (scan.completed_prompts || 0);
  const failed = scan.prompts_failed || 0;
  const total = scan.prompts_selected != null ? scan.prompts_selected : (scan.total_prompts || 0);
  if (failed > 0) {
    document.getElementById("stat-eval-completed").innerText = `${completed} / ${total} (${failed} failed)`;
  } else {
    document.getElementById("stat-eval-completed").innerText = `${completed} / ${total}`;
  }

  const infoBox = document.getElementById("eval-run-info");
  infoBox.style.display = "block";
  document.getElementById("eval-info-id").innerText = (scan.id || "").slice(0, 8);
  const profVerEl = document.getElementById("eval-info-profile-version");
  if (profVerEl) {
    profVerEl.innerText = `v${scan.profile_version || 1}`;
  }
  document.getElementById("eval-info-provider").innerText = (scan.provider || "").toUpperCase();
  document.getElementById("eval-info-model").innerText = scan.model_name || scan.model_identifier || "mock";

  if (scan.duration_seconds != null) {
    document.getElementById("eval-info-duration").innerText = scan.duration_seconds.toFixed(2);
  } else if (scan.completed_at && scan.started_at) {
    const dur = ((new Date(scan.completed_at) - new Date(scan.started_at)) / 1000).toFixed(1);
    document.getElementById("eval-info-duration").innerText = dur;
  } else {
    document.getElementById("eval-info-duration").innerText = "-";
  }
}

async function loadScanResults(scanId) {
  try {
    const res = await fetch(`/api/brands/${currentBrandId}/visibility/scans/${scanId}/results`);
    if (!res.ok) return;
    const data = await res.json();
    currentVisibilityResults = data.results || data.items || [];
    filterVisibilityResults();
  } catch (err) {
    console.error("Failed to load scan results:", err);
  }
}

function filterVisibilityResults() {
  const mentionFilter = document.getElementById("filter-eval-mention").value;
  const recFilter = document.getElementById("filter-eval-rec").value;

  let filtered = currentVisibilityResults;

  if (mentionFilter === "mentioned") {
    filtered = filtered.filter(r => r.brand_mentioned);
  } else if (mentionFilter === "not_mentioned") {
    filtered = filtered.filter(r => !r.brand_mentioned);
  }

  if (recFilter !== "all") {
    filtered = filtered.filter(r => r.recommendation_status === recFilter);
  }

  const container = document.getElementById("eval-results-container");

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; color: var(--text-muted); padding: 2rem;">
        No evaluations match the selected filter criteria.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(r => {
    const isFailed = r.execution_status === "failed";

    let recBadge = "";
    if (isFailed) {
      recBadge = `<span class="badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px dashed rgba(148, 163, 184, 0.4);">UNEVALUATED</span>`;
    } else if (r.recommendation_status === "recommended") {
      recBadge = `<span class="badge" style="background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4);">RECOMMENDED</span>`;
    } else if (r.recommendation_status === "neutral_mention") {
      recBadge = `<span class="badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4);">NEUTRAL MENTION</span>`;
    } else if (r.recommendation_status === "not_recommended") {
      recBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);">NOT RECOMMENDED</span>`;
    } else {
      recBadge = `<span class="badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8;">NOT MENTIONED</span>`;
    }

    let mentionBadge = "";
    if (isFailed) {
      mentionBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);">QUERY FAILED</span>`;
    } else if (r.brand_mentioned) {
      mentionBadge = `<span class="badge badge-completed">MENTIONED</span>`;
    } else {
      mentionBadge = `<span class="badge badge-failed">NOT MENTIONED</span>`;
    }

    const pos = (!isFailed) ? (r.comparative_position || r.comparative_positioning) : null;
    const posChip = pos
      ? `<span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); text-transform: uppercase;">${escapeHtml(pos.replace(/_/g, ' '))}</span>`
      : "";

    const rank = (!isFailed) ? (r.visibility_rank || r.position_in_list) : null;
    const rankChip = rank
      ? `<span class="badge" style="background: #1e293b; color: #facc15; font-weight: 600;">Rank #${rank}</span>`
      : "";

    const competitors = r.competitor_mentions || [];
    const compHtml = competitors.length > 0
      ? `<div style="display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center; margin-top: 0.5rem;">
           <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">Competitors Cited:</span>
           ${competitors.map(c => `<span style="background: #1e293b; border: 1px solid #334155; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; color: #f1f5f9;">${escapeHtml(c)}</span>`).join("")}
         </div>`
      : "";

    const providerCitations = r.provider_citations || [];
    const responseCitations = r.response_citations || (
      providerCitations.length === 0 ? (r.citations || []) : []
    );
    const renderCitationGroup = (label, citations) => citations.length > 0
      ? `<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-top: 0.5rem;">
           <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">${label}:</span>
           ${citations.map(c => {
             const url = typeof c === 'string' ? c : (c.url || '#');
             const title = typeof c === 'string' ? c : (c.title || c.url);
             return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="font-size: 0.75rem; color: var(--accent-primary); background: rgba(59, 130, 246, 0.1); padding: 0.15rem 0.5rem; border-radius: 4px; text-decoration: none; border: 1px solid rgba(59, 130, 246, 0.25);">${escapeHtml(title)}</a>`;
           }).join("")}
         </div>`
      : "";
    const citHtml = providerCitations.length > 0 || responseCitations.length > 0
      ? `${renderCitationGroup("Provider grounding", providerCitations)}${renderCitationGroup("URLs in response", responseCitations)}`
      : "";

    const contextHtml = r.mention_context
      ? `<div style="background: #0f172a; border-left: 3px solid ${r.brand_mentioned ? 'var(--accent-success)' : 'var(--border-color)'}; padding: 0.6rem 0.85rem; border-radius: 0 6px 6px 0; font-size: 0.85rem; color: #cbd5e1; margin-top: 0.6rem; font-style: italic;">
           "${escapeHtml(r.mention_context)}"
         </div>`
      : "";

    const errorHtml = isFailed && r.error_details
      ? `<div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid #ef4444; padding: 0.5rem 0.85rem; border-radius: 0 4px 4px 0; font-size: 0.85rem; color: #fca5a5; margin-top: 0.6rem;">
           <strong>Query Error:</strong> ${escapeHtml(r.error_details)}
         </div>`
      : "";

    return `
      <div class="card" style="margin-bottom: 1rem; padding: 1.25rem; background: #131c2e; border: 1px solid var(--border-color);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
          <div style="flex: 1; min-width: 250px;">
            <div style="font-size: 0.95rem; font-weight: 600; color: #f8fafc; line-height: 1.4;">
              ${escapeHtml(r.prompt_text)}
            </div>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem;">
              ${mentionBadge}
              ${recBadge}
              ${posChip}
              ${rankChip}
            </div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="openRawResponseModal('${r.id}')">
            🔍 Inspect Raw AI Response
          </button>
        </div>

        ${errorHtml}
        ${contextHtml}
        ${compHtml}
        ${citHtml}
      </div>
    `;
  }).join("");
}

function openRawResponseModal(resultId) {
  const result = currentVisibilityResults.find(r => r.id === resultId);
  if (!result) return;

  const model = result.model_name || result.model_identifier || result.provider;
  const latency = result.latency_ms != null ? result.latency_ms : (result.execution_time_ms || 0);
  const status = result.execution_status || 'completed';

  document.getElementById("raw-response-title").innerText = `AI Response: ${model}`;
  document.getElementById("raw-response-meta").innerText = `Provider: ${(result.provider || '').toUpperCase()} | Execution Time: ${latency}ms | Status: ${status.toUpperCase()}`;
  document.getElementById("raw-response-prompt").innerText = result.prompt_text || "";
  document.getElementById("raw-response-body").innerText = result.raw_response_text || "(No response text recorded)";

  document.getElementById("raw-response-modal").style.display = "flex";
}

/* ==========================================================
   GLOBAL BRAND SELECTOR & INITIALIZATION
   ========================================================== */

async function initBrandSelector(targetBrandId = null) {
  try {
    const res = await fetch("/api/brands");
    if (!res.ok) return;
    const brands = await res.json();
    const select = document.getElementById("global-brand-select");
    if (!select) return;

    if (brands.length === 0) {
      select.innerHTML = `<option value="">No brands found</option>`;
      return;
    }

    select.innerHTML = brands.map(b => `
      <option value="${b.id}">${escapeHtml(b.business_name || b.domain)} (${b.domain})</option>
    `).join("");

    const urlParams = new URLSearchParams(window.location.search);
    const paramBrandId = targetBrandId || urlParams.get("brand_id") || currentBrandId;

    if (paramBrandId && brands.some(b => b.id === paramBrandId)) {
      currentBrandId = paramBrandId;
      select.value = paramBrandId;
    } else if (!currentBrandId) {
      currentBrandId = brands[0].id;
      select.value = brands[0].id;
    }

    const urlInput = document.getElementById("exp-website-url");
    if (urlInput && !urlInput.value.trim()) {
      const activeBrand = brands.find(b => b.id === currentBrandId);
      if (activeBrand && activeBrand.domain) {
        urlInput.value = `https://${activeBrand.domain}`;
      }
    }

    if (currentBrandId) {
      await loadBrandProfile(currentBrandId);
    }
  } catch (e) {
    console.error("Failed to init brand selector:", e);
  }
}

async function handleSelectBrand(brandId) {
  if (!brandId) return;
  currentBrandId = brandId;

  const url = new URL(window.location);
  url.searchParams.set("brand_id", brandId);
  window.history.replaceState({}, "", url);

  try {
    const res = await fetch(`/api/brands/${brandId}`);
    if (res.ok) {
      const b = await res.json();
      const urlInput = document.getElementById("exp-website-url");
      if (urlInput && b.domain) {
        urlInput.value = `https://${b.domain}`;
      }
    }
  } catch (e) {}

  const activeBtn = document.querySelector(".nav-btn.active");
  const activeTab = activeBtn ? activeBtn.getAttribute("onclick")?.match(/'([^']+)'/)?.[1] : "profile";
  if (activeTab) {
    switchTab(activeTab);
  }
}

async function initApp() {
  const authed = await checkAuthStatus();
  if (authed) {
    await initBrandSelector();

    // Check for persisted active experiment from URL query or localStorage
    const urlParams = new URLSearchParams(window.location.search);
    const paramScanId = urlParams.get("scan_id");
    let savedExp = null;
    try {
      savedExp = JSON.parse(localStorage.getItem("auralyt_active_experiment") || "null");
    } catch (e) {}

    const activeScanId = paramScanId || savedExp?.scan_id;
    const activeExpBrandId = urlParams.get("brand_id") || savedExp?.brand_id || currentBrandId;

    if (activeExpBrandId && activeScanId) {
      currentBrandId = activeExpBrandId;
      currentScanId = activeScanId;
      switchTab("experiment");
      await loadAndRenderExperimentResults(activeExpBrandId, activeScanId);
    } else {
      switchTab("experiment");
    }
  } else {
    showAuthModal("login");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

