/**
 * Three.js 3D viewer for bikini models.
 * Handles scene setup, OBJ/MTL loading, camera controls, and rendering.
 */

import * as THREE from 'https://unpkg.com/three@0.162.0/build/three.module.js';

// We'll implement OrbitControls and OBJ/MTL loaders inline
// since we're using ES modules from CDN

class SimpleOrbitControls {
    constructor(camera, domElement) {
        this.camera = camera;
        this.domElement = domElement;
        this.target = new THREE.Vector3(0, 1.05, 0);

        this.rotateSpeed = 0.005;
        this.zoomSpeed = 0.001;
        this.panSpeed = 0.002;

        this.spherical = new THREE.Spherical();
        this.sphericalDelta = new THREE.Spherical();

        this._isDragging = false;
        this._isPanning = false;
        this._prevMouse = { x: 0, y: 0 };

        // Initial position
        const offset = camera.position.clone().sub(this.target);
        this.spherical.setFromVector3(offset);

        this._bindEvents();
    }

    _bindEvents() {
        this.domElement.addEventListener('mousedown', (e) => {
            if (e.button === 0) this._isDragging = true;
            if (e.button === 2) this._isPanning = true;
            this._prevMouse = { x: e.clientX, y: e.clientY };
        });

        this.domElement.addEventListener('mousemove', (e) => {
            const dx = e.clientX - this._prevMouse.x;
            const dy = e.clientY - this._prevMouse.y;
            this._prevMouse = { x: e.clientX, y: e.clientY };

            if (this._isDragging) {
                this.spherical.theta -= dx * this.rotateSpeed;
                this.spherical.phi -= dy * this.rotateSpeed;
                this.spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, this.spherical.phi));
                this._updateCamera();
            }

            if (this._isPanning) {
                const right = new THREE.Vector3();
                const up = new THREE.Vector3();
                right.setFromMatrixColumn(this.camera.matrix, 0);
                up.setFromMatrixColumn(this.camera.matrix, 1);
                this.target.addScaledVector(right, -dx * this.panSpeed);
                this.target.addScaledVector(up, dy * this.panSpeed);
                this._updateCamera();
            }
        });

        window.addEventListener('mouseup', () => {
            this._isDragging = false;
            this._isPanning = false;
        });

        this.domElement.addEventListener('wheel', (e) => {
            e.preventDefault();
            this.spherical.radius *= (1 + e.deltaY * this.zoomSpeed);
            this.spherical.radius = Math.max(0.2, Math.min(5, this.spherical.radius));
            this._updateCamera();
        }, { passive: false });

        this.domElement.addEventListener('contextmenu', (e) => e.preventDefault());
    }

    _updateCamera() {
        const offset = new THREE.Vector3().setFromSpherical(this.spherical);
        this.camera.position.copy(this.target).add(offset);
        this.camera.lookAt(this.target);
    }

    update() {
        // Called each frame — currently stateless
    }
}


/**
 * Simple OBJ parser (no external loader dependency)
 */
function parseOBJ(text) {
    const positions = [];
    const normals = [];
    const uvs = [];
    const groups = [];
    let currentGroup = { name: 'default', material: 'default', faces: [] };
    groups.push(currentGroup);

    const lines = text.split('\n');
    for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length === 0) continue;

        switch (parts[0]) {
            case 'v':
                positions.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]));
                break;
            case 'vn':
                normals.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]));
                break;
            case 'vt':
                uvs.push(parseFloat(parts[1]), parseFloat(parts[2]));
                break;
            case 'o':
            case 'g':
                currentGroup = { name: parts[1] || 'default', material: currentGroup.material, faces: [] };
                groups.push(currentGroup);
                break;
            case 'usemtl':
                currentGroup.material = parts[1] || 'default';
                break;
            case 'f':
                const face = [];
                for (let i = 1; i < parts.length; i++) {
                    const indices = parts[i].split('/');
                    face.push({
                        v: parseInt(indices[0]) - 1,
                        vt: indices[1] ? parseInt(indices[1]) - 1 : -1,
                        vn: indices[2] ? parseInt(indices[2]) - 1 : -1,
                    });
                }
                currentGroup.faces.push(face);
                break;
        }
    }

    return { positions, normals, uvs, groups };
}


function objToThreeMesh(parsed, texture, isMetal) {
    const group = new THREE.Group();

    for (const g of parsed.groups) {
        if (g.faces.length === 0) continue;

        const geomPositions = [];
        const geomNormals = [];
        const geomUVs = [];

        for (const face of g.faces) {
            // Triangulate (fan from first vertex)
            for (let i = 1; i < face.length - 1; i++) {
                const tri = [face[0], face[i], face[i + 1]];
                for (const vert of tri) {
                    if (vert.v >= 0 && vert.v * 3 + 2 < parsed.positions.length) {
                        geomPositions.push(
                            parsed.positions[vert.v * 3],
                            parsed.positions[vert.v * 3 + 1],
                            parsed.positions[vert.v * 3 + 2]
                        );
                    }
                    if (vert.vn >= 0 && vert.vn * 3 + 2 < parsed.normals.length) {
                        geomNormals.push(
                            parsed.normals[vert.vn * 3],
                            parsed.normals[vert.vn * 3 + 1],
                            parsed.normals[vert.vn * 3 + 2]
                        );
                    }
                    if (vert.vt >= 0 && vert.vt * 2 + 1 < parsed.uvs.length) {
                        geomUVs.push(
                            parsed.uvs[vert.vt * 2],
                            parsed.uvs[vert.vt * 2 + 1]
                        );
                    }
                }
            }
        }

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(geomPositions, 3));
        if (geomNormals.length > 0) {
            geometry.setAttribute('normal', new THREE.Float32BufferAttribute(geomNormals, 3));
        } else {
            geometry.computeVertexNormals();
        }
        if (geomUVs.length > 0) {
            geometry.setAttribute('uv', new THREE.Float32BufferAttribute(geomUVs, 2));
        }

        let material;
        const isMetalGroup = g.material.includes('metal') || isMetal;

        if (isMetalGroup) {
            material = new THREE.MeshStandardMaterial({
                color: 0xd4af37,
                metalness: 0.9,
                roughness: 0.2,
                side: THREE.DoubleSide,
            });
        } else if (texture) {
            material = new THREE.MeshStandardMaterial({
                map: texture,
                side: THREE.DoubleSide,
                metalness: 0.1,
                roughness: 0.6,
            });
        } else {
            material = new THREE.MeshStandardMaterial({
                color: 0xe94560,
                side: THREE.DoubleSide,
                metalness: 0.1,
                roughness: 0.6,
            });
        }

        const mesh = new THREE.Mesh(geometry, material);
        mesh.name = g.name;
        group.add(mesh);
    }

    return group;
}


export class Viewer {
    constructor(canvas) {
        this.canvas = canvas;
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x0a0a1a);

        // Camera
        const aspect = canvas.clientWidth / canvas.clientHeight;
        this.camera = new THREE.PerspectiveCamera(45, aspect, 0.01, 100);
        this.camera.position.set(0.5, 1.1, 0.8);

        // Renderer
        this.renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: true,
            alpha: false,
        });
        this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.2;

        // Controls
        this.controls = new SimpleOrbitControls(this.camera, canvas);

        // Lights
        this._setupLights();

        // Grid helper
        const grid = new THREE.GridHelper(2, 20, 0x222244, 0x111133);
        grid.position.y = 0.78; // At crotch height (ground reference)
        this.scene.add(grid);

        // Groups for models
        this.garmentGroup = new THREE.Group();
        this.bodyGroup = new THREE.Group();
        this.scene.add(this.garmentGroup);
        this.scene.add(this.bodyGroup);

        this.showBody = true;
        this.wireframe = false;

        // Start render loop
        this._animate();

        // Resize handler
        window.addEventListener('resize', () => this._onResize());
    }

    _setupLights() {
        // Ambient
        const ambient = new THREE.AmbientLight(0x404060, 0.5);
        this.scene.add(ambient);

        // Key light
        const key = new THREE.DirectionalLight(0xfff0e0, 1.2);
        key.position.set(2, 3, 2);
        this.scene.add(key);

        // Fill light
        const fill = new THREE.DirectionalLight(0xe0e0ff, 0.4);
        fill.position.set(-2, 2, -1);
        this.scene.add(fill);

        // Rim light
        const rim = new THREE.DirectionalLight(0xff8080, 0.3);
        rim.position.set(0, 1, -3);
        this.scene.add(rim);
    }

    _animate() {
        requestAnimationFrame(() => this._animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    _onResize() {
        const w = this.canvas.parentElement.clientWidth;
        const h = this.canvas.parentElement.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    async loadGarment(objUrl, textureUrl) {
        // Clear existing
        while (this.garmentGroup.children.length) {
            const child = this.garmentGroup.children[0];
            child.traverse(c => { if (c.geometry) c.geometry.dispose(); if (c.material) c.material.dispose(); });
            this.garmentGroup.remove(child);
        }

        // Load texture
        let texture = null;
        if (textureUrl) {
            const loader = new THREE.TextureLoader();
            texture = await new Promise((resolve) => {
                loader.load(textureUrl, resolve, undefined, () => resolve(null));
            });
            if (texture) {
                texture.wrapS = THREE.RepeatWrapping;
                texture.wrapT = THREE.RepeatWrapping;
            }
        }

        // Load OBJ
        const response = await fetch(objUrl);
        const text = await response.text();
        const parsed = parseOBJ(text);
        const mesh = objToThreeMesh(parsed, texture, false);

        if (this.wireframe) {
            mesh.traverse(child => {
                if (child.isMesh) {
                    child.material.wireframe = true;
                }
            });
        }

        this.garmentGroup.add(mesh);
    }

    async loadBody(objUrl) {
        // Clear existing
        while (this.bodyGroup.children.length) {
            const child = this.bodyGroup.children[0];
            child.traverse(c => { if (c.geometry) c.geometry.dispose(); if (c.material) c.material.dispose(); });
            this.bodyGroup.remove(child);
        }

        const response = await fetch(objUrl);
        const text = await response.text();
        const parsed = parseOBJ(text);
        const mesh = objToThreeMesh(parsed, null, false);

        // Semi-transparent body material
        mesh.traverse(child => {
            if (child.isMesh) {
                child.material = new THREE.MeshStandardMaterial({
                    color: 0xf0d0b0,
                    transparent: true,
                    opacity: 0.3,
                    side: THREE.DoubleSide,
                    metalness: 0.0,
                    roughness: 0.8,
                    wireframe: this.wireframe,
                });
            }
        });

        this.bodyGroup.add(mesh);
        this.bodyGroup.visible = this.showBody;
    }

    setShowBody(show) {
        this.showBody = show;
        this.bodyGroup.visible = show;
    }

    setWireframe(enabled) {
        this.wireframe = enabled;
        [this.garmentGroup, this.bodyGroup].forEach(group => {
            group.traverse(child => {
                if (child.isMesh) {
                    child.material.wireframe = enabled;
                }
            });
        });
    }
}
