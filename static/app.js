/* Pulse - Cloud Monitoring dashboard */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const THEME_KEY = "pulse-theme";

  const numberFormat = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
  });
  const numberFormat2 = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  });

  const state = {
    data: null,
    instance: null,
    hours: 24,
    source: "auto",
    loading: false,
  };

  const chartIds = {
    cpu: "cpu",
    network: "network",
    disk: "disk",
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
    const toggle = $("theme-toggle");
    if (!toggle) return;
    toggle.innerHTML =
      theme === "light"
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
  }

  function initialTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }

  function formatValue(value, unit) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return "—";
    }
    if (unit === "%") return numberFormat.format(value) + "%";
    if (unit === "MB") {
      return (
        (Math.abs(value) < 10 ? numberFormat2 : numberFormat).format(value) +
        " MB"
      );
    }
    if (unit === "ops/s") return numberFormat.format(value) + " ops/s";
    return numberFormat.format(value) + (unit ? " " + unit : "");
  }

  function formatAxisTime(iso, hours) {
    const date = new Date(iso);
    if (hours > 24) {
      return (
        date.toLocaleDateString([], { weekday: "short" }) +
        " " +
        date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    }
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatDateTime(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    return (
      date.toLocaleDateString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    );
  }

  function formatRelative(iso) {
    if (!iso) return "—";
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 45) return "just now";
    if (seconds < 3600) return Math.round(seconds / 60) + " min ago";
    if (seconds < 86400) return Math.round(seconds / 3600) + " hr ago";
    return formatDateTime(iso);
  }

  function mean(values) {
    const usable = values.filter(
      (value) => value !== null && value !== undefined && !Number.isNaN(value)
    );
    if (!usable.length) return 0;
    return usable.reduce((total, value) => total + value, 0) / usable.length;
  }

  function niceMax(value) {
    if (!Number.isFinite(value) || value <= 0) return 1;
    const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
    const normalized = value / magnitude;
    let step;
    if (normalized <= 1) step = 1;
    else if (normalized <= 2) step = 2;
    else if (normalized <= 5) step = 5;
    else step = 10;
    return step * magnitude;
  }

  function svgElement(name, attributes) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes || {}).forEach(([key, value]) => {
      node.setAttribute(key, value);
    });
    return node;
  }

  function buildLinePath(values, xFor, yFor) {
    let path = "";
    let started = false;
    values.forEach((value, index) => {
      if (value === null || value === undefined) {
        started = false;
        return;
      }
      const x = xFor(index);
      const y = yFor(value);
      path += (started ? " L" : " M") + x.toFixed(2) + " " + y.toFixed(2);
      started = true;
    });
    return path.trim();
  }

  function renderChart(container, config) {
    container.innerHTML = "";
    const timestamps = config.timestamps || [];
    const series = (config.series || []).filter((item) => item);
    const allValues = series.flatMap((item) =>
      (item.values || []).filter(
        (value) => value !== null && value !== undefined && !Number.isNaN(value)
      )
    );

    if (!timestamps.length || !allValues.length) {
      const empty = document.createElement("div");
      empty.className = "chart-empty";
      empty.textContent = config.emptyText || "No datapoints in this range";
      container.appendChild(empty);
      return;
    }

    const width = Math.max(container.clientWidth || 640, 260);
    const height = Math.max(container.clientHeight || 220, 120);
    const pad = { top: 14, right: 14, bottom: 26, left: 48 };
    const innerWidth = Math.max(width - pad.left - pad.right, 10);
    const innerHeight = Math.max(height - pad.top - pad.bottom, 10);
    const yMax = niceMax(Math.max(...allValues) * 1.12);
    const yMin = Math.min(0, ...allValues);
    const spanY = yMax - yMin || 1;
    const lastIndex = timestamps.length - 1;

    const xFor = (index) =>
      pad.left +
      (lastIndex === 0 ? innerWidth / 2 : (index / lastIndex) * innerWidth);
    const yFor = (value) =>
      pad.top + innerHeight - ((value - yMin) / spanY) * innerHeight;

    const svg = svgElement("svg", {
      viewBox: "0 0 " + width + " " + height,
      preserveAspectRatio: "none",
      role: "img",
      "aria-label": config.ariaLabel || "Metric chart",
    });

    const defs = svgElement("defs");
    series.forEach((item, index) => {
      const gradient = svgElement("linearGradient", {
        id: "grad-" + chartIds[config.id] + "-" + index,
        x1: "0",
        y1: "0",
        x2: "0",
        y2: "1",
      });
      gradient.appendChild(
        svgElement("stop", {
          offset: "0%",
          "stop-color": item.color,
          "stop-opacity": "0.32",
        })
      );
      gradient.appendChild(
        svgElement("stop", {
          offset: "100%",
          "stop-color": item.color,
          "stop-opacity": "0",
        })
      );
      defs.appendChild(gradient);
    });
    svg.appendChild(defs);

    const tickCount = 4;
    for (let index = 0; index <= tickCount; index += 1) {
      const y = pad.top + (index / tickCount) * innerHeight;
      const value = yMax - (index / tickCount) * spanY;
      svg.appendChild(
        svgElement("line", {
          x1: pad.left,
          y1: y,
          x2: pad.left + innerWidth,
          y2: y,
          class: "grid-line",
        })
      );
      const label = svgElement("text", {
        x: pad.left - 9,
        y: y + 3.5,
        "text-anchor": "end",
        class: "axis-label",
      });
      label.textContent = numberFormat.format(value);
      svg.appendChild(label);
    }

    const xTickCount = width < 440 ? 3 : 5;
    for (let index = 0; index <= xTickCount; index += 1) {
      const dataIndex =
        lastIndex === 0
          ? 0
          : Math.round((index / xTickCount) * lastIndex);
      const x = xFor(dataIndex);
      const label = svgElement("text", {
        x,
        y: height - 7,
        "text-anchor":
          index === 0 ? "start" : index === xTickCount ? "end" : "middle",
        class: "axis-label",
      });
      label.textContent = formatAxisTime(timestamps[dataIndex], config.hours);
      svg.appendChild(label);
    }

    series.forEach((item, index) => {
      const path = buildLinePath(item.values || [], xFor, yFor);
      if (!path) return;
      if (config.fill !== false && series.length === 1) {
        const firstValue = (item.values || []).find(
          (value) => value !== null && value !== undefined
        );
        if (firstValue !== undefined) {
          const areaPath =
            "M " +
            xFor(0).toFixed(2) +
            " " +
            yFor(firstValue).toFixed(2) +
            path +
            " L " +
            xFor(lastIndex).toFixed(2) +
            " " +
            (pad.top + innerHeight) +
            " L " +
            xFor(0).toFixed(2) +
            " " +
            (pad.top + innerHeight) +
            " Z";
          svg.appendChild(
            svgElement("path", {
              d: areaPath,
              fill: "url(#grad-" + chartIds[config.id] + "-" + index + ")",
              class: "series-area",
            })
          );
        }
      }
      svg.appendChild(
        svgElement("path", {
          d: path,
          stroke: item.color,
          class: "series-line",
          "vector-effect": "non-scaling-stroke",
        })
      );
    });

    const hoverLine = svgElement("line", {
      x1: pad.left,
      x2: pad.left,
      y1: pad.top,
      y2: pad.top + innerHeight,
      class: "hover-line",
    });
    svg.appendChild(hoverLine);

    const hoverDots = series.map((item) => {
      const dot = svgElement("circle", {
        r: 4,
        stroke: item.color,
        class: "hover-dot",
      });
      svg.appendChild(dot);
      return dot;
    });

    const overlay = svgElement("rect", {
      x: pad.left,
      y: pad.top,
      width: innerWidth,
      height: innerHeight,
      fill: "transparent",
      style: "cursor: crosshair",
    });
    svg.appendChild(overlay);
    container.appendChild(svg);

    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    container.appendChild(tooltip);

    let activeIndex = -1;
    function updatePosition(index) {
      activeIndex = index;
      const x = xFor(index);
      hoverLine.setAttribute("x1", x);
      hoverLine.setAttribute("x2", x);
      hoverLine.classList.add("visible");

      hoverDots.forEach((dot, seriesIndex) => {
        const value = series[seriesIndex].values[index];
        if (value === null || value === undefined) {
          dot.classList.remove("visible");
          return;
        }
        dot.setAttribute("cx", x);
        dot.setAttribute("cy", yFor(value));
        dot.classList.add("visible");
      });

      const rows = series
        .map((item) => {
          const value = item.values[index];
          return (
            '<div class="tt-row"><span class="tt-dot" style="background:' +
            item.color +
            '"></span>' +
            escapeHtml(item.label) +
            ": <strong>" +
            escapeHtml(formatValue(value, config.unit)) +
            "</strong></div>"
          );
        })
        .join("");
      tooltip.innerHTML =
        '<div class="tt-time">' +
        escapeHtml(formatDateTime(timestamps[index])) +
        "</div>" +
        rows;

      const pointX = (x / width) * container.clientWidth;
      const topValues = series
        .map((item) => item.values[index])
        .filter((value) => value !== null && value !== undefined);
      const pointY = topValues.length
        ? (yFor(Math.max(...topValues)) / height) * container.clientHeight
        : container.clientHeight / 2;
      const clampedX = Math.min(
        Math.max(pointX, 78),
        Math.max(container.clientWidth - 78, 78)
      );
      tooltip.style.left = clampedX + "px";
      tooltip.style.top = Math.max(pointY, 52) + "px";
      tooltip.classList.add("visible");
    }

    function hide() {
      tooltip.classList.remove("visible");
      hoverLine.classList.remove("visible");
      hoverDots.forEach((dot) => dot.classList.remove("visible"));
    }

    svg.addEventListener("mousemove", (event) => {
      const box = svg.getBoundingClientRect();
      if (!box.width) return;
      const localX = (event.clientX - box.left) * (width / box.width);
      const ratio = Math.min(
        Math.max((localX - pad.left) / innerWidth, 0),
        1
      );
      updatePosition(Math.round(ratio * lastIndex));
    });
    svg.addEventListener("mouseleave", hide);
    svg.addEventListener("touchstart", (event) => {
      const touch = event.touches[0];
      if (!touch) return;
      const box = svg.getBoundingClientRect();
      const localX = (touch.clientX - box.left) * (width / box.width);
      const ratio = Math.min(
        Math.max((localX - pad.left) / innerWidth, 0),
        1
      );
      updatePosition(Math.round(ratio * lastIndex));
    });
    svg.addEventListener("touchend", hide);

    container._chart = { updatePosition, hide, activeIndex: () => activeIndex };
  }

  function renderCharts() {
    if (!state.data) return;
    const data = state.data;
    const selected = data.instances.find(
      (item) => item.id === data.selected_instance
    );
    const series = data.series || {};
    const timestamps = data.timestamps || [];
    const hours = data.hours;

    const cpu = series.CPUUtilization || [];
    const networkIn = series.NetworkIn || [];
    const networkOut = series.NetworkOut || [];
    const disk = series.DiskReadOps || [];

    const cpuAvg = mean(cpu);
    const cpuPeak = cpu.length ? Math.max(...cpu.filter((v) => v !== null)) : 0;
    const networkAvgIn = mean(networkIn);
    const networkAvgOut = mean(networkOut);
    const diskAvg = mean(disk);

    $("cpu-chart-sub").textContent =
      (selected ? selected.name : "Selected instance") +
      " · " +
      hours +
      "h window";
    $("cpu-badges").innerHTML =
      '<span class="badge">avg ' +
      escapeHtml(formatValue(cpuAvg, "%")) +
      "</span>" +
      '<span class="badge">peak ' +
      escapeHtml(formatValue(cpuPeak, "%")) +
      "</span>";
    $("network-chart-sub").textContent =
      "avg " +
      formatValue(networkAvgIn, "MB") +
      " in · " +
      formatValue(networkAvgOut, "MB") +
      " out";
    $("disk-chart-sub").textContent = "avg " + formatValue(diskAvg, "ops/s");

    const colors = {};
    (data.metrics || []).forEach((metric) => {
      colors[metric.key] = metric.color;
    });

    renderChart($("chart-cpu"), {
      id: "cpu",
      timestamps,
      series: [
        {
          label: "CPU",
          values: cpu,
          color: colors.CPUUtilization || "#6c8cff",
        },
      ],
      unit: "%",
      hours,
      ariaLabel: "CPU utilization chart",
    });

    renderChart($("chart-network"), {
      id: "network",
      timestamps,
      series: [
        {
          label: "Network In",
          values: networkIn,
          color: colors.NetworkIn || "#22c55e",
        },
        {
          label: "Network Out",
          values: networkOut,
          color: colors.NetworkOut || "#f59e0b",
        },
      ],
      unit: "MB",
      hours,
      fill: false,
      ariaLabel: "Network throughput chart",
    });

    renderChart($("chart-disk"), {
      id: "disk",
      timestamps,
      series: [
        {
          label: "Disk reads",
          values: disk,
          color: colors.DiskReadOps || "#a78bfa",
        },
      ],
      unit: "ops/s",
      hours,
      ariaLabel: "Disk read operations chart",
    });
  }

  function renderStats() {
    const data = state.data;
    const totals = data.totals || {};
    const alerts = data.alerts || [];
    const critical = alerts.filter((item) => item.severity === "critical").length;
    const warning = alerts.filter((item) => item.severity === "warning").length;

    $("stat-instances").textContent = numberFormat.format(totals.instances || 0);
    $("stat-instances-foot").textContent =
      (totals.healthy || 0) +
      " healthy · " +
      Math.max(0, (totals.instances || 0) - (totals.healthy || 0)) +
      " need attention";
    $("stat-avg-cpu").textContent = formatValue(totals.avg_cpu || 0, "%");
    $("stat-avg-cpu-foot").textContent =
      "fleet average over " + data.hours + "h";
    $("stat-peak-cpu").textContent = formatValue(totals.peak_cpu || 0, "%");
    $("stat-peak-cpu-foot").textContent = "highest instance peak";
    $("stat-alerts").textContent = numberFormat.format(alerts.length);
    $("stat-alerts-foot").textContent =
      critical + " critical · " + warning + " warning";
  }

  function renderInstances() {
    const data = state.data;
    const body = $("instances-body");
    const rows = (data.instances || []).map((instance) => {
      const active =
        instance.id === data.selected_instance ? " class=\"active\"" : "";
      return (
        "<tr" +
        active +
        ' data-id="' +
        escapeHtml(instance.id) +
        '">' +
        '<td><div class="inst-name"><span class="inst-dot ' +
        escapeHtml(instance.health) +
        '"></span><span>' +
        escapeHtml(instance.name) +
        '<span class="inst-id">' +
        escapeHtml(instance.id) +
        "</span></span></div></td>" +
        "<td>" +
        escapeHtml(instance.type) +
        "</td>" +
        "<td>" +
        escapeHtml(instance.az) +
        "</td>" +
        '<td class="num">' +
        escapeHtml(formatValue(instance.avg_cpu, "%")) +
        "</td>" +
        '<td class="num">' +
        escapeHtml(formatValue(instance.peak_cpu, "%")) +
        "</td>" +
        '<td class="num">' +
        escapeHtml(formatValue(instance.avg_network, "MB")) +
        "</td>" +
        '<td><span class="health ' +
        escapeHtml(instance.health) +
        '">' +
        escapeHtml(instance.health) +
        "</span></td>" +
        "</tr>"
      );
    });

    body.innerHTML = rows.length
      ? rows.join("")
      : '<tr><td colspan="7"><div class="empty-state">No instances available</div></td></tr>';

    body.querySelectorAll("tr[data-id]").forEach((row) => {
      row.addEventListener("click", () => {
        const id = row.getAttribute("data-id");
        if (!id || id === state.instance) return;
        state.instance = id;
        $("instance-select").value = id;
        loadDashboard();
      });
    });

    const select = $("instance-select");
    select.innerHTML = (data.instances || [])
      .map(
        (instance) =>
          '<option value="' +
          escapeHtml(instance.id) +
          '">' +
          escapeHtml(instance.name) +
          " — " +
          escapeHtml(instance.id) +
          "</option>"
      )
      .join("");
    select.value = data.selected_instance;

    $("fleet-badge").textContent =
      (data.instances || []).length + " instances";
  }

  function alertIcon(severity) {
    if (severity === "info") {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    }
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
  }

  function renderAlerts() {
    const alerts = state.data.alerts || [];
    $("alerts-badge").textContent = String(alerts.length);
    const list = $("alerts-list");
    if (!alerts.length) {
      list.innerHTML =
        '<div class="empty-state">All clear — no threshold breaches detected.</div>';
      return;
    }
    list.innerHTML = alerts
      .map(
        (alert) =>
          '<div class="alert-item ' +
          escapeHtml(alert.severity) +
          '">' +
          '<div class="alert-icon">' +
          alertIcon(alert.severity) +
          "</div>" +
          '<div class="alert-body">' +
          '<div class="alert-instance">' +
          escapeHtml(alert.instance) +
          "</div>" +
          '<div class="alert-message">' +
          escapeHtml(alert.message) +
          "</div>" +
          '<div class="alert-time">' +
          escapeHtml(formatRelative(alert.timestamp)) +
          "</div>" +
          "</div>" +
          "</div>"
      )
      .join("");
  }

  function renderHealth() {
    const instances = state.data.instances || [];
    const counts = { healthy: 0, warning: 0, critical: 0 };
    instances.forEach((instance) => {
      if (counts[instance.health] !== undefined) {
        counts[instance.health] += 1;
      }
    });
    const total = instances.length || 1;
    const segments = ["healthy", "warning", "critical"]
      .filter((key) => counts[key] > 0)
      .map(
        (key) =>
          '<span class="health-seg ' +
          key +
          '" style="width:' +
          (counts[key] / total) * 100 +
          '%"></span>'
      )
      .join("");
    $("health-bar").innerHTML = segments;
    $("health-legend").innerHTML = ["healthy", "warning", "critical"]
      .map(
        (key) =>
          '<span><i class="' +
          key +
          '"></i>' +
          escapeHtml(key) +
          " · " +
          counts[key] +
          "</span>"
      )
      .join("");
  }

  function renderMeta() {
    const data = state.data;
    const warning = data.warning;
    const isLive = data.source === "cloudwatch";
    const pill = $("source-pill");
    const pillText = $("source-pill-text");

    pill.classList.remove("live", "warn");
    if (warning) {
      pill.classList.add("warn");
      pillText.textContent = "Sample fallback";
    } else if (isLive) {
      pill.classList.add("live");
      pillText.textContent = "Live CloudWatch";
    } else {
      pillText.textContent = "Sample data";
    }

    $("page-subtitle").textContent =
      data.selected_name +
      " · " +
      data.hours +
      "h window · updated " +
      formatRelative(data.generated_at);

    $("meta-source").textContent = isLive
      ? "Amazon CloudWatch"
      : "Local sample generator";
    $("meta-source").className = isLive ? "live" : "";
    $("meta-region").textContent = data.region || "—";
    $("meta-period").textContent =
      Math.round((data.period_seconds || 300) / 60) + " minutes";
    $("meta-updated").textContent = formatDateTime(data.generated_at);
    $("meta-cloudwatch").textContent = isLive
      ? "Connected"
      : data.warning
        ? "Unavailable"
        : "Not enabled";
    $("meta-cloudwatch").className = isLive
      ? "live"
      : data.warning
        ? "warn"
        : "";

    $("source-note").textContent = isLive
      ? "Streaming AWS/EC2 metrics through Boto3 and CloudWatch. Values are 5-minute averages for the selected lookback window."
      : "Sample metrics are generated locally. Set CLOUDWATCH_ENABLED=true and AWS credentials to query live EC2 data from your account.";

    const banner = $("warning-banner");
    if (warning) {
      $("warning-text").textContent = warning;
      banner.hidden = false;
    } else {
      $("warning-text").textContent = "";
      banner.hidden = true;
    }

    $("source-sub").textContent = isLive
      ? "Connected to AWS/EC2"
      : data.requested_source === "cloudwatch"
        ? "Requested live metrics"
        : "Demo mode";
  }

  function render() {
    if (!state.data) return;
    renderMeta();
    renderStats();
    renderInstances();
    renderAlerts();
    renderHealth();
    renderCharts();
  }

  function setLoading(isLoading) {
    state.loading = isLoading;
    document.body.classList.toggle("is-loading", isLoading);
    const refresh = $("refresh-btn");
    refresh.classList.toggle("spinning", isLoading);
    refresh.disabled = isLoading;
  }

  async function loadDashboard() {
    const params = new URLSearchParams({
      hours: String(state.hours),
      source: state.source,
    });
    if (state.instance) params.set("instance", state.instance);

    setLoading(true);
    try {
      const response = await fetch("/api/dashboard?" + params.toString(), {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error("Request failed with status " + response.status);
      }
      const data = await response.json();
      state.data = data;
      state.instance = data.selected_instance;
      render();
    } catch (error) {
      const banner = $("warning-banner");
      $("warning-text").textContent =
        "Could not load dashboard data. " + (error.message || "Unknown error");
      banner.hidden = false;
    } finally {
      setLoading(false);
    }
  }

  function debounce(callback, delay) {
    let timer;
    return function debounced() {
      clearTimeout(timer);
      timer = setTimeout(callback, delay);
    };
  }

  function bindEvents() {
    $("theme-toggle").addEventListener("click", () => {
      const next =
        document.documentElement.getAttribute("data-theme") === "light"
          ? "dark"
          : "light";
      applyTheme(next);
      if (state.data) renderCharts();
    });

    $("refresh-btn").addEventListener("click", () => loadDashboard());

    $("instance-select").addEventListener("change", (event) => {
      state.instance = event.target.value;
      loadDashboard();
    });

    $("range-select").addEventListener("change", (event) => {
      state.hours = Number(event.target.value) || 24;
      loadDashboard();
    });

    $("source-select").addEventListener("change", (event) => {
      state.source = event.target.value;
      loadDashboard();
    });

    window.addEventListener(
      "resize",
      debounce(() => {
        if (state.data) renderCharts();
      }, 160)
    );
  }

  applyTheme(initialTheme());
  bindEvents();
  loadDashboard();

  setInterval(() => {
    if (document.visibilityState === "visible" && !state.loading) {
      loadDashboard();
    }
  }, 60000);
})();
