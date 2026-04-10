(function () {
  var SOURCE_LABELS = {
    jbhifi: "JB Hi-Fi",
    target: "Target",
    kmart: "Kmart",
    bigw: "Big W",
  };
  var currentState = null;
  var activeSources = { jbhifi: true, target: true, kmart: true, bigw: true };

  function fmtPrice(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return new Intl.NumberFormat("en-AU", {
      style: "currency",
      currency: "AUD",
    }).format(n);
  }

  function normalizeSource(sourceKey, payload) {
    var sourceName = SOURCE_LABELS[sourceKey] || sourceKey;
    var sourceUrl = (payload && payload.source) || "";
    var inStock = ((payload && payload.in_stock) || []).map(function (p) {
      return Object.assign({}, p, {
        source_key: sourceKey,
        source_name: sourceName,
        source_url: sourceUrl,
      });
    });
    var oos = ((payload && payload.out_of_stock) || []).map(function (p) {
      return Object.assign({}, p, {
        source_key: sourceKey,
        source_name: sourceName,
        source_url: sourceUrl,
      });
    });
    var landed = ((payload && payload.just_landed) || []).map(function (p) {
      return Object.assign({}, p, {
        source_key: sourceKey,
        source_name: sourceName,
        source_url: sourceUrl,
      });
    });
    return { in_stock: inStock, out_of_stock: oos, just_landed: landed };
  }

  function filtered(state) {
    if (!state) return null;
    var activeKeys = Object.keys(activeSources).filter(function (k) { return activeSources[k]; });
    var allActive = activeKeys.length === Object.keys(SOURCE_LABELS).length;
    if (allActive) return state;
    var checked = 0;
    activeKeys.forEach(function (k) {
      checked += (state.products_checked_by_source || {})[k] || 0;
    });
    return {
      in_stock: (state.in_stock || []).filter(function (p) { return activeSources[p.source_key]; }),
      just_landed: (state.just_landed || []).filter(function (p) { return activeSources[p.source_key]; }),
      out_of_stock: (state.out_of_stock || []).filter(function (p) { return activeSources[p.source_key]; }),
      latest_scraped_at: state.latest_scraped_at,
      sources: activeKeys.map(function (k) { return SOURCE_LABELS[k] || k; }),
      products_checked: checked,
      errors_by_source: state.errors_by_source || {},
    };
  }

  function render(state) {
    var metaEl = document.getElementById("meta");
    var errEl = document.getElementById("error");
    var inBody = document.getElementById("inStockBody");
    var landedBody = document.getElementById("landedBody");
    var oosBody = document.getElementById("oosBody");
    var inCount = document.getElementById("inCount");
    var preCount = document.getElementById("preCount");
    var chipPre = document.getElementById("chipPre");
    var landedCount = document.getElementById("landedCount");
    var oosCount = document.getElementById("oosCount");
    var landedSection = document.getElementById("justLandedSection");
    var landedEmpty = document.getElementById("landedEmpty");
    var landedTableWrap = document.getElementById("landedTableWrap");
    var oosSection = document.getElementById("oosSection");

    var visible = filtered(state);

    if (!visible) {
      errEl.hidden = false;
      errEl.textContent =
        "No inventory data. Run the scrapers then reload.";
      inCount.textContent = "0";
      landedCount.textContent = "0";
      oosCount.textContent = "0";
      return;
    }

    errEl.hidden = true;
    errEl.textContent = "";
    metaEl.textContent = [
      "Last scraped: " + (visible.latest_scraped_at || "unknown"),
      "Sources: " + visible.sources.join(", "),
      visible.products_checked ? visible.products_checked + " products checked" : null,
    ]
      .filter(Boolean)
      .join(" · ");

    var inStock = visible.in_stock || [];
    var landed = visible.just_landed || [];
    var oos = visible.out_of_stock || [];

    var preorders = inStock.filter(function (p) { return p.status === "pre-order"; });
    var regularInStock = inStock.filter(function (p) { return p.status !== "pre-order"; });

    inCount.textContent = String(regularInStock.length);
    if (preCount) preCount.textContent = String(preorders.length);
    if (chipPre) chipPre.style.display = preorders.length > 0 ? "" : "none";
    landedCount.textContent = String(landed.length);
    oosCount.textContent = String(oos.length);

    inBody.innerHTML = inStock.map(stockRow).join("");
    landedBody.innerHTML = landed.map(stockRow).join("");
    oosBody.innerHTML = oos.map(oosRow).join("");

    landedSection.classList.toggle("has-items", landed.length > 0);
    landedEmpty.hidden = landed.length > 0;
    landedTableWrap.hidden = landed.length === 0;
    oosSection.style.display = oos.length ? "block" : "none";
  }

  function sourceBadge(p) {
    var key = p.source_key || "";
    var name = escapeHtml(p.source_name || key || "Unknown");
    return '<span class="source-badge ' + escapeAttr(key) + '">' + name + "</span>";
  }

  function stockRow(p) {
    var preorderBadge = "";
    if (p.status === "pre-order") {
      var releaseText = p.release_label ? " · " + escapeHtml(p.release_label) : "";
      preorderBadge = ' <span class="badge-preorder">Pre-order' + releaseText + "</span>";
    }
    return (
      "<tr>" +
      "<td>" + escapeHtml(p.title) + preorderBadge + "</td>" +
      "<td>" + sourceBadge(p) + "</td>" +
      '<td class="price-cell">' + fmtPrice(p.price_aud) + "</td>" +
      '<td class="sku-cell">' + escapeHtml(p.sku || "—") + "</td>" +
      '<td><a class="link-btn" href="' + escapeAttr(p.url) + '" target="_blank" rel="noopener">View ↗</a></td>' +
      "</tr>"
    );
  }

  function oosRow(p) {
    return (
      "<tr>" +
      "<td>" + escapeHtml(p.title) + "</td>" +
      "<td>" + sourceBadge(p) + "</td>" +
      '<td><a class="link-btn" href="' + escapeAttr(p.url) + '" target="_blank" rel="noopener">View ↗</a></td>' +
      "</tr>"
    );
  }

  function escapeHtml(s) {
    if (!s) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function load() {
    document.querySelectorAll(".store-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-source");
        activeSources[key] = !activeSources[key];
        btn.classList.toggle("active", activeSources[key]);
        render(currentState);
      });
    });

    var sources = [];
    if (typeof window.JBHIFI_INVENTORY !== "undefined") {
      sources.push({ key: "jbhifi", payload: window.JBHIFI_INVENTORY });
    }
    if (typeof window.TARGET_INVENTORY !== "undefined") {
      sources.push({ key: "target", payload: window.TARGET_INVENTORY });
    }
    if (typeof window.KMART_INVENTORY !== "undefined") {
      sources.push({ key: "kmart", payload: window.KMART_INVENTORY });
    }
    if (typeof window.BIGW_INVENTORY !== "undefined") {
      sources.push({ key: "bigw", payload: window.BIGW_INVENTORY });
    }
    if (sources.length) {
      currentState = mergeSources(sources);
      render(currentState);
      return;
    }

    Promise.all([
      fetchJson("data/inventory.json", "jbhifi"),
      fetchJson("data/target_inventory.json", "target"),
      fetchJson("data/kmart_inventory.json", "kmart"),
      fetchJson("data/bigw_inventory.json", "bigw"),
    ])
      .then(function (rows) {
        var available = rows.filter(Boolean);
        currentState = available.length ? mergeSources(available) : null;
        render(currentState);
      })
      .catch(function () {
        currentState = null;
        render(currentState);
      });
  }

  function fetchJson(path, key) {
    return fetch(path)
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (payload) {
        return { key: key, payload: payload };
      })
      .catch(function () {
        return null;
      });
  }

  function mergeSources(sourceRows) {
    var inStock = [];
    var landed = [];
    var oos = [];
    var scrapedAts = [];
    var labels = [];
    var checked = 0;
    var checkedBySource = {};
    var errorsBySource = {};

    sourceRows.forEach(function (row) {
      var key = row.key;
      var payload = row.payload || {};
      var normalized = normalizeSource(key, payload);
      inStock = inStock.concat(normalized.in_stock);
      landed = landed.concat(normalized.just_landed);
      oos = oos.concat(normalized.out_of_stock);
      labels.push(SOURCE_LABELS[key] || key);
      if (payload.scraped_at) scrapedAts.push(payload.scraped_at);
      checkedBySource[key] = Number((payload.totals && payload.totals.handles_discovered) || 0);
      errorsBySource[key] = Number((payload.totals && payload.totals.errors) || (payload.errors || []).length || 0);
      if (payload.totals && payload.totals.handles_discovered) {
        checked += Number(payload.totals.handles_discovered) || 0;
      }
    });

    inStock.sort(function (a, b) {
      return String(a.title || "").localeCompare(String(b.title || ""), "en", { sensitivity: "base" });
    });
    oos.sort(function (a, b) {
      return String(a.title || "").localeCompare(String(b.title || ""), "en", { sensitivity: "base" });
    });
    landed.sort(function (a, b) {
      return String(a.title || "").localeCompare(String(b.title || ""), "en", { sensitivity: "base" });
    });

    return {
      in_stock: inStock,
      just_landed: landed,
      out_of_stock: oos,
      latest_scraped_at: scrapedAts.sort().reverse()[0] || null,
      sources: labels,
      products_checked: checked,
      products_checked_by_source: checkedBySource,
      errors_by_source: errorsBySource,
    };
  }

  load();
})();
