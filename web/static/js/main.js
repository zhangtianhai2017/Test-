/**
 * Main UI logic — connects controls to the viewer and API.
 */

import { Viewer } from './viewer.js';

let viewer = null;

// Initialize viewer when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('canvas3d');
    viewer = new Viewer(canvas);

    // Expose to window for inline onclick handlers
    window.generateBikini = generateBikini;

    // Wire up checkboxes
    document.getElementById('chk-body').addEventListener('change', (e) => {
        viewer.setShowBody(e.target.checked);
    });
    document.getElementById('chk-wireframe').addEventListener('change', (e) => {
        viewer.setWireframe(e.target.checked);
    });
});


async function generateBikini(useAI = false) {
    const btnGenerate = document.getElementById('btn-generate');
    const btnAI = document.getElementById('btn-generate-ai');
    const loading = document.getElementById('loading');
    const status = document.getElementById('status');
    const designInfo = document.getElementById('design-info');
    const designDesc = document.getElementById('design-description');
    const designStats = document.getElementById('design-stats');

    // Disable buttons
    btnGenerate.disabled = true;
    btnAI.disabled = true;
    loading.style.display = 'flex';
    status.textContent = 'Generating...';

    try {
        // Get options
        const seedInput = document.getElementById('inp-seed').value;
        const seed = seedInput ? parseInt(seedInput) : null;
        const skipPhysics = !document.getElementById('chk-physics').checked;
        const texRes = parseInt(document.getElementById('inp-texres').value);

        // Call API
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                seed: seed,
                use_ai: useAI,
                skip_physics: skipPhysics,
                texture_resolution: texRes,
            }),
        });

        const data = await response.json();

        if (data.success) {
            // Load garment model
            await viewer.loadGarment(data.obj_url, data.texture_url);

            // Load body model
            if (data.body_url) {
                await viewer.loadBody(data.body_url);
                viewer.setShowBody(document.getElementById('chk-body').checked);
            }

            // Update design info
            designInfo.style.display = 'block';
            designDesc.innerHTML = data.description.split(' | ').map(s =>
                `<div style="margin-bottom:4px">${s}</div>`
            ).join('');
            designStats.innerHTML = [
                `ID: ${data.model_id}`,
                `Time: ${data.generation_time.toFixed(2)}s`,
                `Retries: ${data.retries}`,
                data.metadata.pattern ? `Texture: ${data.metadata.pattern}` : '',
                data.metadata.effect && data.metadata.effect !== 'none' ? `Effect: ${data.metadata.effect}` : '',
            ].filter(Boolean).join('<br>');

            status.textContent = data.message;
        } else {
            status.textContent = `Failed: ${data.message}`;
        }
    } catch (err) {
        status.textContent = `Error: ${err.message}`;
        console.error(err);
    } finally {
        btnGenerate.disabled = false;
        btnAI.disabled = false;
        loading.style.display = 'none';
    }
}

// Make available globally for onclick handlers
window.generateBikini = generateBikini;
