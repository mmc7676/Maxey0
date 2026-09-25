/* graph3d.js — a small perspective renderer for the semantic field.
 *
 * Deliberately dependency-free: this page is served by a stdlib Python server
 * on loopback, and a CDN import would make an offline install fail at exactly
 * the moment someone wants to look at their own data. Canvas 2D plus real
 * projection math is enough for a few hundred nodes.
 *
 * Coordinates arrive already meaningful — x/y are trilaterated against Maxey0's
 * anchor field, z is the hierarchy level — so this file only rotates, projects
 * and draws. It never invents a layout.
 */
(function (global) {
  "use strict";

  function sub(a, b) { return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z }; }
  function cross(a, b) {
    return {
      x: a.y * b.z - a.z * b.y,
      y: a.z * b.x - a.x * b.z,
      z: a.x * b.y - a.y * b.x
    };
  }
  function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function norm(v) {
    const m = Math.hypot(v.x, v.y, v.z) || 1;
    return { x: v.x / m, y: v.y / m, z: v.z / m };
  }

  const LEVEL_STYLE = {
    concept: { r: 7.5, fill: "#6ea8fe", glow: "rgba(110,168,254,.55)" },
    skill:   { r: 4.5, fill: "#8b5cf6", glow: "rgba(139,92,246,.45)" },
    agent:   { r: 3.2, fill: "#4ade80", glow: "rgba(74,222,128,.35)" }
  };

  class Field3D {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.data = { nodes: [], edges: [], anchors: [], levels: [] };
      this.visible = { concept: true, skill: true, agent: true, edges: true };
      this.selected = null;
      this.hover = null;
      this.onSelect = null;
      this.onHover = null;

      // Spherical camera. Elevation is clamped short of the poles so the
      // up-vector never degenerates and flips the scene.
      this.cam = { az: -0.62, el: 0.42, dist: 620, target: { x: 0, y: 0, z: 0 } };
      this.home = Object.assign({}, this.cam);

      this._projected = [];
      this._dpr = 1;

      this._bindEvents();
      this.resize();
    }

    setData(data) {
      this.data = data;
      this.draw();
    }

    setVisible(key, on) {
      this.visible[key] = on;
      this.draw();
    }

    resetCamera() {
      this.cam = Object.assign({}, this.home);
      this.draw();
    }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      const dpr = global.devicePixelRatio || 1;
      this._dpr = dpr;
      this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
      this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
      this.W = rect.width;
      this.H = rect.height;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.draw();
    }

    /* ── camera basis + projection ─────────────────────────────────── */
    _basis() {
      const { az, el, dist, target } = this.cam;
      const ce = Math.cos(el);
      const eye = {
        x: target.x + dist * ce * Math.cos(az),
        y: target.y + dist * ce * Math.sin(az),
        z: target.z + dist * Math.sin(el)
      };
      const fwd = norm(sub(target, eye));
      // World up is +z; guard the degenerate case even though el is clamped.
      let up = { x: 0, y: 0, z: 1 };
      if (Math.abs(dot(fwd, up)) > 0.999) up = { x: 0, y: 1, z: 0 };
      const right = norm(cross(fwd, up));
      const camUp = cross(right, fwd);
      return { eye, fwd, right, up: camUp };
    }

    _project(p, basis) {
      const d = sub(p, basis.eye);
      const vz = dot(d, basis.fwd);
      if (vz <= 1) return null;                       // behind or on the lens
      const focal = this.H * 0.9;
      const s = focal / vz;
      return {
        x: this.W / 2 + dot(d, basis.right) * s,
        y: this.H / 2 - dot(d, basis.up) * s,
        depth: vz,
        scale: s
      };
    }

    /* ── drawing ───────────────────────────────────────────────────── */
    // Synchronous on purpose. An earlier version coalesced through
    // requestAnimationFrame, which silently never fires while the page is not
    // compositing (background tab, hidden pane, paused compositor) -- so the
    // very first paint could be dropped and the view stayed blank until some
    // later input happened to land. A few hundred nodes of canvas 2D costs
    // well under a frame, so there is nothing to coalesce away, and drawing
    // straight through removes that whole failure mode.
    draw() {
      this._draw();
    }

    _draw() {
      const ctx = this.ctx;
      const basis = this._basis();
      ctx.clearRect(0, 0, this.W, this.H);

      const nodes = this.data.nodes.filter(n => this.visible[n.level]);
      const byId = new Map();
      const projected = [];

      for (const n of nodes) {
        const p = this._project(n, basis);
        if (!p) continue;
        const rec = { node: n, p };
        byId.set(n.id, rec);
        projected.push(rec);
      }
      this._projected = projected;

      this._drawPlanes(ctx, basis);
      this._drawAnchors(ctx, basis);

      if (this.visible.edges) {
        ctx.lineWidth = 0.6;
        for (const e of this.data.edges) {
          const a = byId.get(e.source), b = byId.get(e.target);
          if (!a || !b) continue;
          const lit = this.selected &&
            (e.source === this.selected || e.target === this.selected);
          ctx.strokeStyle = lit ? "rgba(110,168,254,.85)" : "rgba(120,140,180,.10)";
          ctx.lineWidth = lit ? 1.4 : 0.6;
          ctx.beginPath();
          ctx.moveTo(a.p.x, a.p.y);
          ctx.lineTo(b.p.x, b.p.y);
          ctx.stroke();
        }
      }

      // Painter's algorithm: far nodes first so near ones occlude them.
      projected.sort((a, b) => b.p.depth - a.p.depth);
      for (const rec of projected) this._drawNode(ctx, rec);
    }

    _drawPlanes(ctx, basis) {
      const half = 210;
      for (const lv of this.data.levels || []) {
        if (!this.visible[lv.level]) continue;
        const corners = [
          { x: -half, y: -half, z: lv.z }, { x: half, y: -half, z: lv.z },
          { x: half, y: half, z: lv.z }, { x: -half, y: half, z: lv.z }
        ].map(c => this._project(c, basis));
        if (corners.some(c => !c)) continue;
        ctx.strokeStyle = "rgba(110,168,254,.13)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(corners[0].x, corners[0].y);
        for (let i = 1; i < corners.length; i++) ctx.lineTo(corners[i].x, corners[i].y);
        ctx.closePath();
        ctx.stroke();

        const label = this._project({ x: -half, y: -half, z: lv.z }, basis);
        if (label) {
          ctx.fillStyle = "rgba(147,161,187,.65)";
          ctx.font = "11px ui-monospace, monospace";
          ctx.fillText(lv.label, label.x + 4, label.y - 5);
        }
      }
    }

    _drawAnchors(ctx, basis) {
      for (const a of this.data.anchors || []) {
        // An anchor is a field position, not a node: draw it as a vertical
        // spine through all three planes, which is what it actually is.
        const bottom = this._project({ x: a.x, y: a.y, z: -140 }, basis);
        const top = this._project({ x: a.x, y: a.y, z: 140 }, basis);
        if (!bottom || !top) continue;
        ctx.strokeStyle = a.color + "44";
        ctx.lineWidth = 1.2;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(bottom.x, bottom.y);
        ctx.lineTo(top.x, top.y);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = a.color;
        ctx.globalAlpha = 0.9;
        ctx.beginPath();
        ctx.arc(top.x, top.y, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = a.color + "cc";
        ctx.font = "10px ui-monospace, monospace";
        ctx.fillText(a.id, top.x + 6, top.y - 4);
      }
    }

    _drawNode(ctx, rec) {
      const { node, p } = rec;
      const style = LEVEL_STYLE[node.level] || LEVEL_STYLE.agent;
      // Perspective-correct size, floored so distant agents stay clickable.
      const r = Math.max(1.6, style.r * (p.scale * 1.15));
      const isSel = this.selected === node.id;
      const isHov = this.hover === node.id;

      if (isSel || isHov) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, r + 6, 0, Math.PI * 2);
        ctx.fillStyle = style.glow;
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = node.unanchored ? "#63708a" : style.fill;
      ctx.globalAlpha = node.unanchored ? 0.5 : 1;
      ctx.fill();
      ctx.globalAlpha = 1;

      if (isSel) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1.6;
        ctx.stroke();
      }

      // Only concepts get a permanent label; everything else would be noise.
      if (node.level === "concept" || isSel || isHov) {
        ctx.fillStyle = isSel || isHov ? "#dbe3f0" : "rgba(219,227,240,.8)";
        ctx.font = (isSel ? "600 " : "") + "11px system-ui, sans-serif";
        ctx.fillText(node.label, p.x + r + 5, p.y + 3.5);
      }
    }

    /* ── interaction ───────────────────────────────────────────────── */
    _pick(mx, my) {
      let best = null, bestD = 16;   // generous radius: agents render small
      for (const rec of this._projected) {
        const d = Math.hypot(rec.p.x - mx, rec.p.y - my);
        if (d < bestD) { bestD = d; best = rec; }
      }
      return best;
    }

    _bindEvents() {
      const c = this.canvas;
      let dragging = false, lastX = 0, lastY = 0, moved = 0;

      c.addEventListener("pointerdown", e => {
        dragging = true; moved = 0;
        lastX = e.clientX; lastY = e.clientY;
        c.setPointerCapture(e.pointerId);
      });

      c.addEventListener("pointermove", e => {
        const rect = c.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;

        if (dragging) {
          const dx = e.clientX - lastX, dy = e.clientY - lastY;
          moved += Math.abs(dx) + Math.abs(dy);
          lastX = e.clientX; lastY = e.clientY;
          this.cam.az -= dx * 0.006;
          const lim = Math.PI / 2 - 0.08;
          this.cam.el = Math.max(-lim, Math.min(lim, this.cam.el + dy * 0.006));
          this.draw();
          return;
        }

        const hit = this._pick(mx, my);
        const id = hit ? hit.node.id : null;
        if (id !== this.hover) {
          this.hover = id;
          this.draw();
          if (this.onHover) {
            this.onHover(hit ? hit.node : null, mx, my);
          }
        } else if (hit && this.onHover) {
          this.onHover(hit.node, mx, my);
        }
      });

      const end = e => {
        if (!dragging) return;
        dragging = false;
        try { c.releasePointerCapture(e.pointerId); } catch (_) {}
        if (moved < 5) {                       // a click, not the end of a drag
          const rect = c.getBoundingClientRect();
          const hit = this._pick(e.clientX - rect.left, e.clientY - rect.top);
          this.selected = hit ? hit.node.id : null;
          this.draw();
          if (this.onSelect) this.onSelect(hit ? hit.node : null);
        }
      };
      c.addEventListener("pointerup", end);
      c.addEventListener("pointercancel", end);

      c.addEventListener("wheel", e => {
        e.preventDefault();
        const f = e.deltaY > 0 ? 1.1 : 0.9;
        this.cam.dist = Math.max(160, Math.min(2200, this.cam.dist * f));
        this.draw();
      }, { passive: false });

      c.addEventListener("pointerleave", () => {
        if (this.hover !== null) {
          this.hover = null;
          this.draw();
          if (this.onHover) this.onHover(null, 0, 0);
        }
      });

      global.addEventListener("resize", () => this.resize());
    }
  }

  global.Field3D = Field3D;
})(window);
