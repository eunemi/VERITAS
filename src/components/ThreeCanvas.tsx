"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";

export default function ThreeCanvas() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 8;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xfff8f0, 1.5);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 3);
    directionalLight.position.set(10, 15, 10);
    directionalLight.castShadow = true;
    scene.add(directionalLight);

    const newspaperGroup = new THREE.Group();
    scene.add(newspaperGroup);

    // Newspaper Geometry
    const pageGeom = new THREE.BoxGeometry(3, 4.5, 0.01);
    const pageMat = new THREE.MeshPhongMaterial({
      color: 0xf4efe6,
      shininess: 5,
    });

    // Create a "folded" stack
    for (let i = 0; i < 8; i++) {
      const page = new THREE.Mesh(pageGeom, pageMat);
      page.position.set(0, 0, i * 0.02);
      page.rotation.z = (Math.random() - 0.5) * 0.05;
      page.rotation.y = (Math.random() - 0.5) * 0.05;
      newspaperGroup.add(page);
    }

    let animationFrameId: number;

    function animate() {
      animationFrameId = requestAnimationFrame(animate);

      // Slow cinematic rotation
      newspaperGroup.rotation.y = Math.sin(Date.now() * 0.0005) * 0.2;
      newspaperGroup.rotation.x = Math.cos(Date.now() * 0.0003) * 0.1;

      renderer.render(scene, camera);
    }

    animate();

    const handleResize = () => {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
      // cleanup geometries and materials
      pageGeom.dispose();
      pageMat.dispose();
      renderer.dispose();
    };
  }, []);

  return <div ref={mountRef} className="w-full h-full" />;
}
