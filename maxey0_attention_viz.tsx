<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Maxey0 SuperAgent - Attention Latent Space</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Monaco', 'Consolas', monospace;
        }
        
        body {
            background: linear-gradient(135deg, #0a0a0a, #1a1a2e, #16213e);
            color: #00ff88;
            overflow: hidden;
        }
        
        #visualization-container {
            position: relative;
            width: 100vw;
            height: 100vh;
        }
        
        #canvas-container {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        
        .control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.9);
            border: 2px solid #00ff88;
            border-radius: 10px;
            padding: 20px;
            width: 90%;
            max-width: 350px;
            backdrop-filter: blur(10px);
            font-size: 12px;
            z-index: 100;
        }
        
        .spectrum-analyzer {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.9);
            border: 2px solid #ffaa00;
            border-radius: 10px;
            padding: 20px;
            width: 90%;
            max-width: 300px;
            backdrop-filter: blur(10px);
            font-size: 12px;
            z-index: 100;
            display: none;
        }
        
        .memory-monitor {
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.9);
            border: 2px solid #4488ff;
            border-radius: 10px;
            padding: 15px;
            width: 90%;
            max-width: 400px;
            backdrop-filter: blur(10px);
            font-size: 11px;
            z-index: 100;
        }
        
        input, textarea, select, button {
            width: 100%;
            padding: 8px;
            margin: 5px 0;
            background: rgba(0, 40, 80, 0.8);
            border: 1px solid #00ff88;
            border-radius: 5px;
            color: #00ff88;
            font-family: inherit;
            font-size: 11px;
        }
        
        button {
            background: rgba(0, 80, 40, 0.9);
            cursor: pointer;
            transition: all 0.3s;
        }
        
        button:hover {
            background: rgba(0, 120, 60, 0.9);
            box-shadow: 0 0 10px #00ff88;
        }
        
        .spectrum-bar {
            display: inline-block;
            width: 20px;
            margin: 1px;
            background: linear-gradient(to top, #ff4444, #ffaa00, #00ff88);
            border-radius: 2px;
            transition: height 0.3s;
        }
        
        .memory-tier {
            display: inline-block;
            padding: 4px 8px;
            margin: 2px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
        }
        
        .persistent { background: #00ff88; color: #000; }
        .episodic { background: #ffaa00; color: #000; }
        .scratchpad { background: #ff4444; color: #fff; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 10px 0;
        }
        
        .reflex-indicator {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
        }
        
        .stable { background: #00ff88; }
        .watch { background: #ffaa00; }
        .quarantine { background: #ff4444; animation: blink 1s infinite; }
        
        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0.3; }
        }
        
        .agent-status {
            font-size: 10px;
            margin: 5px 0;
            padding: 5px;
            background: rgba(0, 60, 120, 0.3);
            border-radius: 3px;
        }
        
        @media (max-width: 768px) {
            .control-panel, .memory-monitor {
                font-size: 10px;
                padding: 10px;
            }
            .spectrum-analyzer {
                right: 20px;
                left: 20px;
                max-width: none;
            }
        }
    </style>
</head>
<body>
    <div id="visualization-container">
        <div id="canvas-container"></div>
        
        <div class="control-panel">
            <h2 style="color: #00ff88; margin-bottom: 15px;">MAXEY0 SUPERAGENT</h2>
            <p style="font-size: 10px; margin-bottom: 10px;">Structured Context Windows - Attention Analysis</p>
            
            <label>Input Sequence:</label>
            <textarea id="input-text" rows="3">The magnitude spectrum attention mechanism detects hallucinations through oscillatory drift</textarea>
            
            <div class="stats-grid">
                <label><input type="checkbox" id="show-spectrum"> Show Spectrum</label>
                <label><input type="checkbox" id="show-flow" checked> Show Flow</label>
            </div>
            
            <label>Memory Tier Filter:</label>
            <select id="memory-filter">
                <option value="all">All Tiers</option>
                <option value="persistent">Persistent</option>
                <option value="episodic">Episodic</option>
                <option value="scratchpad">Scratchpad</option>
            </select>
            
            <button onclick="regenerateVisualization()">Regenerate</button>
            <button onclick="runReflexAnalysis()">Run Reflex Analysis</button>
            
            <div style="margin-top: 15px; font-size: 10px;">
                <div>System Statistics:</div>
                <div id="system-stats"></div>
            </div>
            
            <div style="margin-top: 10px;">
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <div style="width: 12px; height: 12px; background: #00ff88; border-radius: 50%; margin-right: 5px;"></div>
                    Persistent
                </div>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <div style="width: 12px; height: 12px; background: #ffaa00; border-radius: 50%; margin-right: 5px;"></div>
                    Episodic
                </div>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <div style="width: 12px; height: 12px; background: #ff4444; border-radius: 50%; margin-right: 5px;"></div>
                    Scratchpad
                </div>
            </div>
        </div>
        
        <div class="spectrum-analyzer" id="spectrum-analyzer">
            <h3 style="color: #ffaa00; margin-bottom: 10px;">MAGNITUDE SPECTRUM</h3>
            <div id="selected-token-info"></div>
            <div id="spectral-components"></div>
            <div id="token-details"></div>
        </div>
        
        <div class="memory-monitor">
            <h3 style="color: #4488ff; margin-bottom: 10px;">MEMRE MONITOR</h3>
            <div class="agent-status">
                <span class="reflex-indicator stable"></span>Maxey React: Dependencies patched
            </div>
            <div class="agent-status">
                <span class="reflex-indicator stable"></span>Maxey ThreeJS: Native renderer active
            </div>
            <div class="agent-status">
                <span class="reflex-indicator stable"></span>Maxey0: SCW reflexes enabled
            </div>
            <div id="memory-stats"></div>
        </div>
    </div>

    <script>
        let scene, camera, renderer, tokens = [], edges = [], selectedToken = null;
        let animationId;
        
        class Maxey0AttentionPlatform {
            constructor() {
                this.initializeScene();
                this.generateTokenData();
                this.setupEventListeners();
                this.animate();
            }
            
            initializeScene() {
                scene = new THREE.Scene();
                scene.background = new THREE.Color(0x0a0a0a);
                
                camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
                camera.position.set(25, 25, 25);
                camera.lookAt(0, 0, 0);
                
                renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
                renderer.setSize(window.innerWidth, window.innerHeight);
                renderer.shadowMap.enabled = true;
                
                document.getElementById('canvas-container').appendChild(renderer.domElement);
                
                const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
                scene.add(ambientLight);
                
                const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
                directionalLight.position.set(10, 10, 10);
                scene.add(directionalLight);
                
                const pointLight = new THREE.PointLight(0x00ff88, 0.8, 100);
                pointLight.position.set(-10, -10, -10);
                scene.add(pointLight);
                
                this.setupMouseControls();
            }
            
            setupMouseControls() {
                let mouseDown = false;
                let mouseX = 0;
                let mouseY = 0;
                
                renderer.domElement.addEventListener('mousedown', function(event) {
                    mouseDown = true;
                    mouseX = event.clientX;
                    mouseY = event.clientY;
                });
                
                renderer.domElement.addEventListener('mouseup', function() {
                    mouseDown = false;
                });
                
                let self = this;
                renderer.domElement.addEventListener('mousemove', function(event) {
                    if (!mouseDown) return;
                    
                    const deltaX = event.clientX - mouseX;
                    const deltaY = event.clientY - mouseY;
                    
                    const spherical = new THREE.Spherical();
                    spherical.setFromVector3(camera.position);
                    spherical.theta -= deltaX * 0.01;
                    spherical.phi += deltaY * 0.01;
                    spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi));
                    
                    camera.position.setFromSpherical(spherical);
                    camera.lookAt(0, 0, 0);
                    
                    mouseX = event.clientX;
                    mouseY = event.clientY;
                });
                
                renderer.domElement.addEventListener('wheel', function(event) {
                    const scale = event.deltaY > 0 ? 1.1 : 0.9;
                    camera.position.multiplyScalar(scale);
                });
                
                renderer.domElement.addEventListener('click', function(event) {
                    self.handleTokenSelection(event);
                });
            }
            
            generateTokenData() {
                const inputText = document.getElementById('input-text').value;
                const words = inputText.split(/\s+/).filter(function(t) { return t.length > 0; });
                
                tokens.forEach(function(token) {
                    if (token.mesh) scene.remove(token.mesh);
                    if (token.label) scene.remove(token.label);
                });
                tokens = [];
                
                for (let i = 0; i < words.length; i++) {
                    const token = this.createToken(words[i], i);
                    tokens.push(token);
                    scene.add(token.mesh);
                    if (token.label) scene.add(token.label);
                }
                
                this.generateAttentionEdges();
                this.updateStatistics();
            }
            
            createToken(word, index) {
                const x = (Math.random() - 0.5) * 30;
                const y = (Math.random() - 0.5) * 30;
                const z = (Math.random() - 0.5) * 30;
                
                const baseAttention = Math.random() * 0.8 + 0.2;
                const spectralComponents = [];
                for (let i = 0; i < 8; i++) {
                    spectralComponents.push(Math.random() * 0.5);
                }
                
                let sii = 0;
                for (let i = 0; i < spectralComponents.length; i++) {
                    const comp = spectralComponents[i];
                    const idx = i;
                    sii += Math.pow(comp * Math.sin(idx * Math.PI / 4), 2);
                }
                sii = sii / spectralComponents.length;
                
                const stability = Math.max(0, 1 - sii);
                let memoryTier = 'scratchpad';
                if (sii < 0.3) {
                    memoryTier = 'persistent';
                } else if (sii < 0.6) {
                    memoryTier = 'episodic';
                }
                
                let reflexState = 'STABLE';
                if (sii > 0.8) {
                    reflexState = 'QUARANTINE';
                } else if (sii > 0.5) {
                    reflexState = 'WATCH';
                }
                
                let color = 0xff4444;
                if (memoryTier === 'persistent') {
                    color = 0x00ff88;
                } else if (memoryTier === 'episodic') {
                    color = 0xffaa00;
                }
                
                const geometry = new THREE.SphereGeometry(baseAttention * 2 + 0.5, 16, 16);
                const material = new THREE.MeshStandardMaterial({
                    color: color,
                    transparent: true,
                    opacity: stability * 0.8 + 0.2,
                    emissive: reflexState === 'QUARANTINE' ? 0x330000 : 0x000000,
                    emissiveIntensity: reflexState === 'QUARANTINE' ? 0.3 : 0
                });
                
                const mesh = new THREE.Mesh(geometry, material);
                mesh.position.set(x, y, z);
                mesh.userData = { tokenIndex: index };
                
                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                canvas.width = 256;
                canvas.height = 64;
                
                let labelColor = '#ff4444';
                if (memoryTier === 'persistent') {
                    labelColor = '#00ff88';
                } else if (memoryTier === 'episodic') {
                    labelColor = '#ffaa00';
                }
                
                context.fillStyle = labelColor;
                context.font = '24px Monaco';
                context.textAlign = 'center';
                context.fillText(word, 128, 32);
                
                const labelTexture = new THREE.CanvasTexture(canvas);
                const labelMaterial = new THREE.SpriteMaterial({ map: labelTexture });
                const label = new THREE.Sprite(labelMaterial);
                label.position.set(x, y + baseAttention * 2 + 2, z);
                label.scale.set(4, 1, 1);
                
                return {
                    word: word,
                    position: [x, y, z],
                    attention: baseAttention,
                    sii: sii,
                    stability: stability,
                    memoryTier: memoryTier,
                    reflexState: reflexState,
                    spectralComponents: spectralComponents,
                    anchorDistance: Math.random() * 2,
                    mesh: mesh,
                    label: label,
                    index: index
                };
            }
            
            generateAttentionEdges() {
                edges.forEach(function(edge) {
                    if (edge.line) scene.remove(edge.line);
                });
                edges = [];
                
                if (!document.getElementById('show-flow').checked) return;
                
                for (let i = 0; i < tokens.length; i++) {
                    for (let j = i + 1; j < Math.min(i + 4, tokens.length); j++) {
                        const weight = Math.exp(-Math.abs(i - j)) * Math.random();
                        if (weight > 0.3) {
                            const points = [
                                new THREE.Vector3(tokens[i].position[0], tokens[i].position[1], tokens[i].position[2]),
                                new THREE.Vector3(tokens[j].position[0], tokens[j].position[1], tokens[j].position[2])
                            ];
                            
                            const geometry = new THREE.BufferGeometry().setFromPoints(points);
                            const material = new THREE.LineBasicMaterial({
                                color: 0x4488ff,
                                transparent: true,
                                opacity: weight * 0.6
                            });
                            
                            const line = new THREE.Line(geometry, material);
                            scene.add(line);
                            
                            edges.push({ from: i, to: j, weight: weight, line: line });
                        }
                    }
                }
            }
            
            handleTokenSelection(event) {
                const mouse = new THREE.Vector2();
                mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
                mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
                
                const raycaster = new THREE.Raycaster();
                raycaster.setFromCamera(mouse, camera);
                
                const meshes = [];
                for (let i = 0; i < tokens.length; i++) {
                    meshes.push(tokens[i].mesh);
                }
                const intersects = raycaster.intersectObjects(meshes);
                
                if (intersects.length > 0) {
                    const tokenIndex = intersects[0].object.userData.tokenIndex;
                    selectedToken = tokens[tokenIndex];
                    this.showSpectrumAnalyzer();
                } else {
                    selectedToken = null;
                    this.hideSpectrumAnalyzer();
                }
            }
            
            showSpectrumAnalyzer() {
                if (!selectedToken) return;
                
                const analyzer = document.getElementById('spectrum-analyzer');
                analyzer.style.display = 'block';
                
                let infoHtml = '<h4>Token: "' + selectedToken.word + '"</h4>';
                infoHtml += '<div style="margin: 10px 0;">';
                infoHtml += '<div>Attention: ' + selectedToken.attention.toFixed(3) + '</div>';
                infoHtml += '<div>SII: ' + selectedToken.sii.toFixed(3) + '</div>';
                infoHtml += '<div>Stability: ' + selectedToken.stability.toFixed(3) + '</div>';
                infoHtml += '<div>Memory Tier: <span class="memory-tier ' + selectedToken.memoryTier + '">' + selectedToken.memoryTier + '</span></div>';
                infoHtml += '<div>Reflex State: <span class="reflex-indicator ' + selectedToken.reflexState.toLowerCase() + '"></span>' + selectedToken.reflexState + '</div>';
                infoHtml += '</div>';
                
                document.getElementById('selected-token-info').innerHTML = infoHtml;
                
                let spectrumHtml = '';
                for (let i = 0; i < selectedToken.spectralComponents.length; i++) {
                    const comp = selectedToken.spectralComponents[i];
                    const height = comp * 60 + 10;
                    spectrumHtml += '<div class="spectrum-bar" style="height: ' + height + 'px;" title="Freq ' + i + ': ' + comp.toFixed(3) + '"></div>';
                }
                
                document.getElementById('spectral-components').innerHTML = '<h4>FFT Spectrum:</h4><div style="margin: 10px 0;">' + spectrumHtml + '</div>';
                
                const posStr = selectedToken.position.map(function(p) { return p.toFixed(1); }).join(', ');
                let detailsHtml = '<div style="font-size: 10px; color: #888;">';
                detailsHtml += '<div>Position: [' + posStr + ']</div>';
                detailsHtml += '<div>Anchor Distance: ' + selectedToken.anchorDistance.toFixed(3) + '</div>';
                detailsHtml += '<div>Conservation: Total attention = ' + selectedToken.attention.toFixed(3) + '</div>';
                detailsHtml += '</div>';
                
                document.getElementById('token-details').innerHTML = detailsHtml;
            }
            
            hideSpectrumAnalyzer() {
                document.getElementById('spectrum-analyzer').style.display = 'none';
            }
            
            updateStatistics() {
                let totalAttention = 0;
                let avgSII = 0;
                let stableCount = 0;
                let quarantineCount = 0;
                
                for (let i = 0; i < tokens.length; i++) {
                    totalAttention += tokens[i].attention;
                    avgSII += tokens[i].sii;
                    if (tokens[i].reflexState === 'STABLE') stableCount++;
                    if (tokens[i].reflexState === 'QUARANTINE') quarantineCount++;
                }
                avgSII = avgSII / tokens.length;
                
                let statsHtml = '<div>Total Attention: ' + totalAttention.toFixed(3) + '</div>';
                statsHtml += '<div>Average SII: ' + avgSII.toFixed(3) + '</div>';
                statsHtml += '<div>Stable Tokens: ' + stableCount + '</div>';
                statsHtml += '<div>Quarantined: ' + quarantineCount + '</div>';
                
                document.getElementById('system-stats').innerHTML = statsHtml;
                
                let persistentCount = 0;
                let episodicCount = 0;
                let scratchpadCount = 0;
                
                for (let i = 0; i < tokens.length; i++) {
                    if (tokens[i].memoryTier === 'persistent') persistentCount++;
                    if (tokens[i].memoryTier === 'episodic') episodicCount++;
                    if (tokens[i].memoryTier === 'scratchpad') scratchpadCount++;
                }
                
                let memoryHtml = '<div style="margin-top: 10px;">';
                memoryHtml += '<div>Persistent: ' + persistentCount + ' tokens</div>';
                memoryHtml += '<div>Episodic: ' + episodicCount + ' tokens</div>';
                memoryHtml += '<div>Scratchpad: ' + scratchpadCount + ' tokens</div>';
                memoryHtml += '</div>';
                
                document.getElementById('memory-stats').innerHTML = memoryHtml;
            }
            
            setupEventListeners() {
                let self = this;
                
                document.getElementById('input-text').addEventListener('input', function() {
                    self.generateTokenData();
                });
                
                document.getElementById('show-flow').addEventListener('change', function() {
                    self.generateAttentionEdges();
                });
                
                document.getElementById('memory-filter').addEventListener('change', function(e) {
                    self.applyMemoryFilter(e.target.value);
                });
                
                window.addEventListener('resize', function() {
                    camera.aspect = window.innerWidth / window.innerHeight;
                    camera.updateProjectionMatrix();
                    renderer.setSize(window.innerWidth, window.innerHeight);
                });
            }
            
            applyMemoryFilter(filter) {
                for (let i = 0; i < tokens.length; i++) {
                    const token = tokens[i];
                    if (filter === 'all' || token.memoryTier === filter) {
                        token.mesh.visible = true;
                        if (token.label) token.label.visible = true;
                    } else {
                        token.mesh.visible = false;
                        if (token.label) token.label.visible = false;
                    }
                }
            }
            
            animate() {
                let self = this;
                animationId = requestAnimationFrame(function() { self.animate(); });
                
                for (let i = 0; i < tokens.length; i++) {
                    const token = tokens[i];
                    if (token.mesh) {
                        token.mesh.rotation.y += 0.01;
                        if (selectedToken === token) {
                            token.mesh.scale.setScalar(1.2);
                        } else {
                            token.mesh.scale.setScalar(1.0);
                        }
                    }
                }
                
                renderer.render(scene, camera);
            }
        }
        
        function regenerateVisualization() {
            platform.generateTokenData();
        }
        
        function runReflexAnalysis() {
            for (let i = 0; i < tokens.length; i++) {
                const token = tokens[i];
                if (token.sii > 0.8) {
                    token.reflexState = 'QUARANTINE';
                    token.mesh.material.emissive.setHex(0x330000);
                    token.mesh.material.emissiveIntensity = 0.5;
                }
            }
            platform.updateStatistics();
        }
        
        let platform;
        window.addEventListener('load', function() {
            platform = new Maxey0AttentionPlatform();
        });
    </script>
</body>
</html>