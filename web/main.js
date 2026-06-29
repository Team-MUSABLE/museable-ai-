/* ============================================================
 * museable A4 — 웹 3D 핀 매트릭스 뷰 (본선 메인 산출물)
 *
 * 핵심 규칙(제안서/계약 준수):
 *  - 핀 높이 = 백엔드가 준 H 양자화값(0..LEVELS-1) 그대로 매핑 (가짜 연출 X)
 *  - 작품 선택 → 각 핀이 H까지 실시간 상승 (행렬별 시차 ease)
 *  - 확대(ROI 변경) → 핀 전부 0으로 내림 → 새 H로 재상승
 *  - 백엔드(/api) 있으면 거기서 H, 없으면 JS 합성 H로 폴백 (file:// 에서도 동작)
 * ============================================================ */

/* ---- 계약 기본값 (백엔드 응답이 오면 거기 값으로 덮어씀) ---- */
let COLS = 48, ROWS = 32, LEVELS = 16;

/* ---- three 셋업 ---- */
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0c0e12);

const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
camera.position.set(0, 16, 20);

const controls = new THREE.OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.target.set(0, -3.2, 0);   // 시선을 아래로 → 디바이스가 화면 위쪽에 위치(하단 도슨트 패널 안 가림)
controls.minDistance = 10; controls.maxDistance = 40;

scene.add(new THREE.AmbientLight(0xffffff, 0.35));
const key = new THREE.DirectionalLight(0xfff1dc, 1.25);
key.position.set(-8, 16, 10); scene.add(key);
const rim = new THREE.DirectionalLight(0x8fb8ff, 0.5);
rim.position.set(10, 6, -8); scene.add(rim);

/* ---- 베이스 플레이트 (디바이스 본체) ---- */
const PIN_GAP = 0.46;                     // 핀 간격
const W = COLS * PIN_GAP, D = ROWS * PIN_GAP;
const plate = new THREE.Mesh(
  new THREE.BoxGeometry(W + 1.6, 0.8, D + 1.6),
  new THREE.MeshStandardMaterial({ color: 0x111419, roughness: 0.7, metalness: 0.3 })
);
plate.position.y = -0.4; scene.add(plate);

/* ---- 핀: InstancedMesh (실린더 n×m) ---- */
let pinMesh, N;
const PIN_R = 0.16, PIN_MAXH = 4.2;       // 핀 반지름 / 최대 상승 높이(시각)
const dummy = new THREE.Object3D();
let curH, tgtH, velH;                      // 현재/목표/속도 (스프링)

function buildPins() {
  if (pinMesh) { scene.remove(pinMesh); pinMesh.geometry.dispose(); pinMesh.material.dispose(); }
  N = COLS * ROWS;
  const geo = new THREE.CylinderGeometry(PIN_R, PIN_R, 1, 10);
  geo.translate(0, 0.5, 0);                // 밑면이 베이스에 닿도록 (위로 자람)
  const mat = new THREE.MeshStandardMaterial({ color: 0xb9bcc4, roughness: 0.45, metalness: 0.6 });
  pinMesh = new THREE.InstancedMesh(geo, mat, N);
  pinMesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(N * 3), 3);
  scene.add(pinMesh);
  curH = new Float32Array(N); tgtH = new Float32Array(N); velH = new Float32Array(N);
  document.getElementById('stPins').textContent = N;
  document.getElementById('cGrid').textContent = `${COLS}×${ROWS}`;
  document.getElementById('cLv').textContent = LEVELS;
}

function pinXZ(x, y) {
  return [(x - (COLS - 1) / 2) * PIN_GAP, (y - (ROWS - 1) / 2) * PIN_GAP];
}

/* ---- H(정수 0..LEVELS-1, row-major) 적용 ---- */
function setTarget(data) {
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    const i = y * COLS + x;
    tgtH[i] = (data[i] / (LEVELS - 1)) * PIN_MAXH;   // 양자화값 → 시각 높이
  }
}
function dropAll() { for (let i = 0; i < N; i++) tgtH[i] = 0; }

/* ---- 렌더 루프 (스프링 상승 + 색 음영) ---- */
const cBase = new THREE.Color(0x9a9ea7), cHi = new THREE.Color(0xf3e6cf);
let spin = false;
function frame() {
  requestAnimationFrame(frame);
  if (spin) { scene.rotation.y += 0.0035; }
  for (let i = 0; i < N; i++) {
    // 오버슈트 없는 완만한 상승: 목표를 향해 천천히 수렴 (작을수록 느림)
    curH[i] += (tgtH[i] - curH[i]) * 0.045;
    const h = Math.max(0.04, curH[i]);
    const x = i % COLS, y = (i / COLS) | 0, [px, pz] = pinXZ(x, y);
    dummy.position.set(px, 0, pz); dummy.scale.set(1, h, 1); dummy.updateMatrix();
    pinMesh.setMatrixAt(i, dummy.matrix);
    const t = Math.min(1, curH[i] / PIN_MAXH);
    const col = cBase.clone().lerp(cHi, t * t);
    pinMesh.setColorAt(i, col);
  }
  pinMesh.instanceMatrix.needsUpdate = true;
  if (pinMesh.instanceColor) pinMesh.instanceColor.needsUpdate = true;
  controls.update();
  renderer.render(scene, camera);
}

/* ---- 데이터: 백엔드 우선, 실패 시 JS 합성 ---- */
const FALLBACK = [
  { id: 'buddha_01', title: '금동 반가사유상', era: '삼국시대 7세기', type: '3d', kind: 'face' },
  { id: 'celadon_01', title: '청자 상감운학문 매병', era: '고려 12세기', type: '3d', kind: 'dome' },
  { id: 'ssireum_01', title: '김홍도 「씨름」', era: '조선 18세기', type: '2d', kind: 'edges' },
];
let useBackend = false, artworks = FALLBACK, current = null;

async function loadArtworks() {
  try {
    const r = await fetch('/api/artworks', { signal: AbortSignal.timeout(800) });
    if (!r.ok) throw 0;
    artworks = await r.json(); useBackend = true;
  } catch { artworks = FALLBACK; useBackend = false; }
  document.getElementById('stSrc').textContent = useBackend ? '백엔드 /api' : 'JS 합성(폴백)';
  renderList();
}

async function getHeightmap(art) {
  if (useBackend) {
    const r = await fetch(`/api/artworks/${art.id}/heightmap`);
    const j = await r.json();
    COLS = j.cols; ROWS = j.rows; LEVELS = j.levels;
    return j.data;
  }
  return synthH(art.kind);                 // 폴백: 계약과 동일 포맷(정수 0..LEVELS-1)
}

/* JS 합성 H — pipeline/relief.py 와 동일 컨셉 (백엔드 없이도 시연 가능) */
function synthH(kind) {
  const data = new Int16Array(COLS * ROWS);
  const cx = (COLS - 1) / 2, cy = (ROWS - 1) / 2;
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    let h;
    const rx = (x - cx), ry = (y - cy);
    if (kind === 'face') {
      const r = Math.hypot(rx / (COLS * 0.32), (ry + 2) / (ROWS * 0.38));
      h = Math.pow(Math.max(0, 1 - r), 0.7);
      const crown = Math.exp(-((rx / (COLS * 0.18)) ** 2 + ((ry + ROWS * 0.34) / (ROWS * 0.10)) ** 2));
      h = Math.max(h, crown * 0.85);
    } else if (kind === 'edges') {
      const r = Math.hypot(rx / COLS, ry / ROWS);
      h = (0.5 + 0.5 * Math.sin(r * 26)) * Math.max(0, 1 - r * 1.6);
    } else {
      const r = Math.hypot(rx / (COLS * 0.42), ry / (ROWS * 0.42));
      h = Math.max(0, 1 - r * r);
    }
    data[y * COLS + x] = Math.round(Math.min(1, Math.max(0, h)) * (LEVELS - 1));
  }
  return Array.from(data);
}

/* ---- UI ---- */
const listEl = document.getElementById('artList');
function renderList() {
  listEl.innerHTML = '';
  artworks.forEach(a => {
    const b = document.createElement('div'); b.className = 'art'; b.id = 'a-' + a.id;
    const badge = a.real === false ? ' <span style="color:#caa05a">· 합성 예시</span>' : '';
    b.innerHTML = `<div class="t">${a.title}</div><div class="s">${a.era} · ${a.type === '2d' ? '회화(윤곽 relief)' : '입체 유물'}${badge}</div>`;
    b.onclick = () => selectArt(a);
    const del = document.createElement('div'); del.className = 'del'; del.textContent = '✕'; del.title = '삭제';
    del.onclick = (e) => { e.stopPropagation(); deleteArt(a); };
    b.appendChild(del);
    listEl.appendChild(b);
  });
}
async function deleteArt(a) {
  if (!confirm(`「${a.title}」 삭제할까요?`)) return;
  if (useBackend) {
    try { await fetch(`/api/artworks/${a.id}`, { method: 'DELETE' }); }
    catch (e) { alert('삭제 실패: ' + e); return; }
  } else {
    artworks = artworks.filter(x => x.id !== a.id);
  }
  if (current && current.id === a.id) { current = null; document.getElementById('btnReset').onclick(); }
  if (useBackend) await loadArtworks(); else renderList();
}

function selectArt(a) {
  current = a;
  document.querySelectorAll('.art').forEach(e => e.classList.remove('on'));
  document.getElementById('a-' + a.id).classList.add('on');
  document.getElementById('hudTitle').textContent = a.title;
  document.getElementById('hudSub').textContent = '「핀 올리기」를 누르면 H까지 상승';
}

async function raise(roiScale = 1) {
  if (!current) selectArt(artworks[0]);
  dropAll();                               // 규칙: 먼저 0으로 내림
  await new Promise(r => setTimeout(r, 180));
  const data = await getHeightmap(current);
  if (data.length !== COLS * ROWS) buildPins();   // 격자 바뀌면 재생성
  setTarget(data);
  document.getElementById('hudSub').textContent =
    `핀 ${COLS}×${ROWS} 상승 중 · 높이=H 양자화값 (FPGA 동일 값)`;
  loadDocent();
}

/* ---- AI 도슨트 (EXAONE, 백엔드 경유) ---- */
const dtext = document.getElementById('dtext');
const dq = document.getElementById('dq');
const dsend = document.getElementById('dsend');

async function loadDocent() {
  if (!useBackend) { dtext.textContent = '도슨트는 백엔드(/api) 실행 시 EXAONE로 생성됩니다.'; return; }
  dtext.textContent = '도슨트 생성 중…  (분석 중)';
  try {
    const r = await fetch(`/api/artworks/${current.id}/docent`);
    const j = await r.json();
    const text = j.text || '(빈 응답)';
    dtext.textContent = text;
    showSources(j.sources, j.grounded);
    speak(text);                 // 도슨트 낭독 (브라우저 TTS)
    playAmbience(current.id);    // 작품 분위기음 (VARCO text2sound, 배경)
  } catch (e) { dtext.textContent = '도슨트 생성 실패: ' + e; }
}

/* 도슨트 낭독 — 브라우저 한국어 TTS (키 불필요) */
function speak(t) {
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(t); u.lang = 'ko-KR'; u.rate = 1.02;
    speechSynthesis.speak(u);
  } catch {}
}

/* VARCO 분위기음 — 배경으로 작게 재생 (키 없으면 503 → 조용히 무시) */
async function playAmbience(id) {
  if (!useBackend) return;
  const audio = document.getElementById('audio'), tag = document.getElementById('audioTag');
  try {
    const r = await fetch(`/api/artworks/${id}/ambience`);
    if (!r.ok) { tag.style.display = 'none'; return; }
    audio.src = URL.createObjectURL(await r.blob());
    audio.volume = 0.35; audio.loop = true; tag.style.display = '';
    audio.play().catch(() => {});
  } catch { tag.style.display = 'none'; }
}

function showSources(sources, grounded) {
  const el = document.getElementById('dsrc');
  if (grounded && sources && sources.length)
    el.textContent = '📚 근거(RAG): ' + sources.join(' · ');
  else
    el.textContent = grounded === false ? '⚠ RAG 코퍼스 없음 — 일반 지식 기반(검증 안 됨)' : '';
}

async function askQuestion() {
  const q = dq.value.trim();
  if (!q || !current) return;
  if (!useBackend) { dtext.textContent = '질문 응답은 백엔드(/api) 실행 시 가능합니다.'; return; }
  dsend.disabled = true; const prev = dtext.textContent;
  dtext.textContent = `Q. ${q}\n\n생성 중…`;
  try {
    const r = await fetch(`/api/artworks/${current.id}/ask`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    });
    const j = await r.json();
    dtext.textContent = `Q. ${q}\n\n${j.answer || '(빈 응답)'}`;
    showSources(j.sources, j.grounded);
    dq.value = '';
  } catch (e) { dtext.textContent = prev + '\n\n질문 실패: ' + e; }
  dsend.disabled = false;
}
dsend.onclick = askQuestion;
dq.addEventListener('keydown', e => { if (e.key === 'Enter') askQuestion(); });

document.getElementById('btnRaise').onclick = () => raise();
document.getElementById('zoom').oninput = () => raise();   // ROI 변경 → 내렸다 재상승 (A4 규칙)
document.getElementById('btnSpin').onclick = function () { spin = !spin; this.classList.toggle('on', spin); };
document.getElementById('btnReset').onclick = () => {
  dropAll(); spin = false; document.getElementById('btnSpin').classList.remove('on');
  scene.rotation.y = 0;
  try { speechSynthesis.cancel(); } catch {}
  const a = document.getElementById('audio'); a.pause(); a.removeAttribute('src');
  document.getElementById('hudTitle').textContent = '작품을 고르고 「핀 올리기」';
  document.getElementById('hudSub').textContent = '';
};

/* ---- 작품 등록 (사진 업로드 → 핀) ---- */
const upBtn = document.getElementById('upBtn'), upMsg = document.getElementById('upMsg');
upBtn.onclick = async () => {
  if (!useBackend) { upMsg.textContent = '업로드는 백엔드(/api) 실행 시 가능합니다.'; return; }
  const f = document.getElementById('upFile').files[0];
  const title = document.getElementById('upTitle').value.trim() || '무제';
  if (!f) { upMsg.textContent = '사진을 선택하세요.'; return; }
  const fd = new FormData();
  fd.append('title', title);
  fd.append('era', document.getElementById('upEra').value.trim());
  fd.append('type', document.getElementById('upType').value);
  fd.append('image', f);
  upBtn.disabled = true;
  upMsg.textContent = '사진 분석 중… 배경제거 → 3D 생성(최대 1~2분) → 핀 H. 터미널 로그 참고.';
  try {
    const r = await fetch('/api/artworks', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(await r.text());
    const art = await r.json();
    await loadArtworks();          // 목록 갱신
    selectArt(artworks.find(a => a.id === art.id) || art);
    upMsg.textContent = '등록 완료 → 「핀 올리기」를 누르세요.';
    raise();                       // 바로 핀 상승
  } catch (e) { upMsg.textContent = '실패: ' + e; }
  upBtn.disabled = false;
};

/* ---- 리사이즈 ---- */
function resize() {
  const m = document.querySelector('main');
  renderer.setSize(m.clientWidth, m.clientHeight, false);
  camera.aspect = m.clientWidth / m.clientHeight; camera.updateProjectionMatrix();
}
addEventListener('resize', resize);

/* ---- 시작 ---- */
buildPins(); resize(); frame(); loadArtworks();
