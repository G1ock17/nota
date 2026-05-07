const brandsDataNode = document.getElementById("brands-data");
const BRANDS = brandsDataNode ? JSON.parse(brandsDataNode.textContent) : [];

let query = "";

const searchInput = document.getElementById("searchInput");
const brandsMain = document.getElementById("brandsMain");
const noResults = document.getElementById("noResults");
const countNum = document.getElementById("countNum");
const totalCount = document.getElementById("totalCount");
const alphaStrip = document.getElementById("alphaStrip");
const catalogUrl = (brandsMain?.dataset.catalogUrl || "/products/").trim();

if (searchInput) {
  function filteredBrands() {
    return BRANDS.filter((b) => {
      const q = query.trim().toLowerCase();
      return !q || b.name.toLowerCase().includes(q) || b.origin.toLowerCase().includes(q);
    });
  }

  function buildAlphaStrip(brands) {
    const letters = new Set(brands.map((b) => b.name[0].toUpperCase()));
    const allLetters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
    alphaStrip.innerHTML = allLetters.map((l) => {
      const has = letters.has(l);
      return `<a href="#letter-${l}" class="alph ${has ? "has-items" : "disabled"}">${l}</a>`;
    }).join("");
  }

  function highlight(name, q) {
    if (!q) return name;
    const idx = name.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return name;
    return `${name.slice(0, idx)}<mark style="background:rgba(51,5,7,.12);color:var(--wine);border-radius:1px">${name.slice(idx, idx + q.length)}</mark>${name.slice(idx + q.length)}`;
  }

  function render() {
    const brands = filteredBrands();
    countNum.textContent = brands.length;

    const sections = brandsMain.querySelectorAll(".letter-section");
    sections.forEach((s) => s.remove());

    if (!brands.length) {
      noResults.classList.add("visible");
      alphaStrip.style.display = "none";
      return;
    }

    noResults.classList.remove("visible");
    alphaStrip.style.display = "";

    const grouped = {};
    brands.forEach((b) => {
      const letter = b.name[0].toUpperCase();
      if (!grouped[letter]) grouped[letter] = [];
      grouped[letter].push(b);
    });

    buildAlphaStrip(brands);

    const sortedLetters = Object.keys(grouped).sort();
    sortedLetters.forEach((letter, li) => {
      const sec = document.createElement("div");
      sec.className = "letter-section rev";
      sec.id = `letter-${letter}`;
      sec.style.transitionDelay = `${li * 0.04}s`;

      const items = grouped[letter];
      sec.innerHTML = `
        <div class="letter-head">
          <div class="letter-char">${letter}</div>
          <div class="letter-line"></div>
          <div class="letter-count">${items.length} ${items.length === 1 ? "бренд" : items.length < 5 ? "бренда" : "брендов"}</div>
        </div>
        <div class="brands-grid">
          ${items.map((b) => {
            const hl = query ? highlight(b.name, query) : b.name;
            const brandSlug = b.slug;
            const href = `${catalogUrl}?brand=${encodeURIComponent(brandSlug)}`;
            return `
              <a href="${href}" class="brand-card ${b.featured ? "featured" : ""}">
                <div class="bc-top">
                  <div class="bc-initial">${b.name[0]}</div>
                </div>
                <div class="bc-name">${hl}</div>
                <div class="bc-bottom">
                  <div class="bc-origin">${b.origin}</div>
                  <div class="bc-arrow">→</div>
                </div>
              </a>`;
          }).join("")}
        </div>`;

      brandsMain.insertBefore(sec, noResults);
    });

    requestAnimationFrame(() => {
      brandsMain.querySelectorAll(".rev").forEach((el) => {
        setTimeout(() => el.classList.add("on"), 10);
      });
    });
  }

  searchInput.addEventListener("input", () => {
    query = searchInput.value;
    render();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== searchInput) {
      e.preventDefault();
      searchInput.focus();
    }
    if (e.key === "Escape") {
      searchInput.value = "";
      query = "";
      render();
    }
  });

  document.addEventListener("click", (e) => {
    const a = e.target.closest(".alph");
    if (!a || !a.classList.contains("has-items")) return;
    e.preventDefault();
    const target = document.querySelector(a.getAttribute("href"));
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  totalCount.textContent = BRANDS.length;
  render();
}
