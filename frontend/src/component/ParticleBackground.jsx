import React, { useEffect, useRef } from "react";

export default function ParticleBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    let animId;
    let w, h;
    let mouse = { x: -1000, y: -1000 };
    const particles = [];
    const PARTICLE_COUNT = 70;
    const CONNECTION_DIST = 130;
    const MOUSE_RADIUS = 160;

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    function handleMouse(e) {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    }
    window.addEventListener("mousemove", handleMouse);

    // Blue / cyan / purple palette matching the design system
    const colors = [
      { h: 217, s: 91, l: 60 },  // #3b82f6
      { h: 187, s: 96, l: 42 },  // #06b6d4
      { h: 258, s: 90, l: 66 },  // #8b5cf6
      { h: 210, s: 60, l: 55 },  // softer blue
      { h: 200, s: 70, l: 50 },  // teal accent
    ];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const c = colors[Math.floor(Math.random() * colors.length)];
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.5 + 0.5,
        color: c,
        alpha: Math.random() * 0.4 + 0.15,
        pulseSpeed: Math.random() * 0.012 + 0.004,
        pulsePhase: Math.random() * Math.PI * 2,
      });
    }

    function draw(time) {
      ctx.clearRect(0, 0, w, h);

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Mouse interaction — gentle repulsion
        const dxM = p.x - mouse.x;
        const dyM = p.y - mouse.y;
        const distM = Math.sqrt(dxM * dxM + dyM * dyM);
        if (distM < MOUSE_RADIUS) {
          const force = (1 - distM / MOUSE_RADIUS) * 0.02;
          p.vx += dxM * force;
          p.vy += dyM * force;
        }

        // Damping
        p.vx *= 0.994;
        p.vy *= 0.994;

        p.x += p.vx;
        p.y += p.vy;

        // Wrap edges
        if (p.x < -10) p.x = w + 10;
        if (p.x > w + 10) p.x = -10;
        if (p.y < -10) p.y = h + 10;
        if (p.y > h + 10) p.y = -10;

        const pulseAlpha = p.alpha + Math.sin(time * p.pulseSpeed + p.pulsePhase) * 0.1;
        const { h: ch, s, l } = p.color;

        // Glow
        const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
        grad.addColorStop(0, `hsla(${ch}, ${s}%, ${l}%, ${pulseAlpha * 0.7})`);
        grad.addColorStop(0.5, `hsla(${ch}, ${s}%, ${l}%, ${pulseAlpha * 0.15})`);
        grad.addColorStop(1, `hsla(${ch}, ${s}%, ${l}%, 0)`);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Core dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${ch}, ${s}%, ${l + 15}%, ${pulseAlpha})`;
        ctx.fill();
      }

      // Connection lines
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < CONNECTION_DIST) {
            const alpha = (1 - dist / CONNECTION_DIST) * 0.08;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `hsla(217, 60%, 60%, ${alpha})`;
            ctx.lineWidth = 0.6;
            ctx.stroke();
          }
        }
      }

      animId = requestAnimationFrame(draw);
    }

    animId = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", handleMouse);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        zIndex: 0,
        pointerEvents: "none",
      }}
    />
  );
}
