(function () {
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.querySelector(".nav");
    if (toggle && nav) {
        toggle.addEventListener("click", function () {
            var open = nav.classList.toggle("is-open");
            nav.classList.toggle("hidden", !open);
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        });

        nav.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                nav.classList.remove("is-open");
                nav.classList.add("hidden");
                toggle.setAttribute("aria-expanded", "false");
            });
        });
    }

    var revealItems = document.querySelectorAll(".reveal");
    if (revealItems.length) {
        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("is-visible");
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.16 }
        );

        revealItems.forEach(function (item) {
            observer.observe(item);
        });
    }

    document.body.addEventListener("htmx:afterSwap", function (e) {
        var t = e.detail && e.detail.target;
        if (!t || t.id !== "cart-toast") return;
        window.clearTimeout(t._toastHide);
        t._toastHide = window.setTimeout(function () {
            t.innerHTML = "";
        }, 4500);
    });

    document.querySelectorAll("[data-product-gallery]").forEach(function (gallery) {
        var main = gallery.querySelector("[data-gallery-main]");
        var thumbs = gallery.querySelectorAll("[data-gallery-thumb]");
        if (!main || !thumbs.length) return;

        thumbs.forEach(function (thumb) {
            thumb.addEventListener("click", function () {
                var nextSrc = thumb.getAttribute("data-image-url");
                var nextAlt = thumb.getAttribute("data-image-alt") || main.alt;
                if (!nextSrc || nextSrc === main.getAttribute("src")) return;

                thumbs.forEach(function (el) {
                    el.classList.remove("is-active");
                });
                thumb.classList.add("is-active");

                main.classList.add("is-fading");
                window.setTimeout(function () {
                    main.setAttribute("src", nextSrc);
                    main.setAttribute("alt", nextAlt);
                    main.classList.remove("is-fading");
                }, 160);
            });
        });
    });

    var sidebar = document.getElementById("catalog-sidebar-filters");

    function normalizeForModalSearch(s) {
        if (s == null || s === "") return "";
        var t = String(s).replace(/-/g, " ").normalize("NFD");
        try {
            t = t.replace(/\p{M}/gu, "");
        } catch (e) {
            t = t.replace(/[\u0300-\u036f]/g, "");
        }
        return t.toLowerCase().replace(/\s+/g, " ").trim();
    }

    function modalFilterHaystack(row) {
        var parts = [];
        var attr = row.getAttribute("data-filter-text");
        if (attr) parts.push(attr);
        var inp = row.querySelector('input[type="checkbox"]');
        if (inp && inp.value) parts.push(inp.value);
        var text = (row.textContent || "").replace(/\s+/g, " ").trim();
        if (text) parts.push(text);
        return normalizeForModalSearch(parts.join(" "));
    }

    function filterModalList(modal, query) {
        if (!modal) return;
        var q = normalizeForModalSearch((query || "").trim());
        var isNotes = modal.id === "filter-modal-notes";
        var body = modal.querySelector(".filter-modal__body");
        var rows = body
            ? body.querySelectorAll(".js-modal-filter-row")
            : modal.querySelectorAll(".js-modal-filter-row");

        if (!q) {
            rows.forEach(function (row) {
                row.classList.remove("is-filter-match-hidden");
            });
            if (isNotes) {
                modal.querySelectorAll(".js-modal-notes-section").forEach(
                    function (sec) {
                        sec.hidden = false;
                        sec.removeAttribute("hidden");
                    }
                );
            }
            return;
        }

        rows.forEach(function (row) {
            var hay = modalFilterHaystack(row);
            var match = hay.indexOf(q) !== -1;
            row.classList.toggle("is-filter-match-hidden", !match);
        });

        if (isNotes) {
            modal.querySelectorAll(".js-modal-notes-section").forEach(
                function (sec) {
                    var visible = false;
                    sec.querySelectorAll(".js-modal-filter-row").forEach(
                        function (r) {
                            if (!r.classList.contains("is-filter-match-hidden")) {
                                visible = true;
                            }
                        }
                    );
                    sec.hidden = !visible;
                }
            );
        }
    }

    function syncBrandsModalFromSidebar() {
        var modal = document.getElementById("filter-modal-brands");
        if (!modal || !sidebar) return;
        modal.querySelectorAll(".js-modal-brand").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="brand"][value="' + cb.value + '"]'
            );
            cb.checked = !!(side && side.checked);
        });
    }

    function syncNotesModalFromSidebar() {
        var modal = document.getElementById("filter-modal-notes");
        if (!modal || !sidebar) return;
        modal.querySelectorAll(".js-modal-note").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="notes"][value="' + cb.value + '"]'
            );
            cb.checked = !!(side && side.checked);
        });
    }

    function closeFilterModal(which) {
        var id =
            which === "brands" ? "filter-modal-brands" : "filter-modal-notes";
        var m = document.getElementById(id);
        if (!m) return;
        m.classList.remove("is-open");
        m.setAttribute("aria-hidden", "true");
        if (!document.querySelector(".filter-modal.is-open")) {
            document.body.style.overflow = "";
        }
    }

    function closeAllFilterModals() {
        document.querySelectorAll(".filter-modal.is-open").forEach(function (m) {
            m.classList.remove("is-open");
            m.setAttribute("aria-hidden", "true");
        });
        document.body.style.overflow = "";
    }

    function openFilterModal(which) {
        closeAllFilterModals();
        if (which === "brands") syncBrandsModalFromSidebar();
        else if (which === "notes") syncNotesModalFromSidebar();
        var id =
            which === "brands" ? "filter-modal-brands" : "filter-modal-notes";
        var m = document.getElementById(id);
        if (!m) return;
        m.classList.add("is-open");
        m.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
        var searchInp = m.querySelector(".filter-modal__search");
        if (searchInp) {
            searchInp.value = "";
            filterModalList(m, "");
        }
    }

    function onFilterModalSearchInput(e) {
        var t = e.target;
        if (!t || !t.classList || !t.classList.contains("filter-modal__search")) return;
        var modal = t.closest(".filter-modal");
        if (modal) filterModalList(modal, t.value);
    }

    document.body.addEventListener("input", onFilterModalSearchInput, true);
    document.body.addEventListener("search", onFilterModalSearchInput, true);
    document.body.addEventListener(
        "compositionend",
        onFilterModalSearchInput,
        true
    );

    function applyBrandsModal() {
        var modal = document.getElementById("filter-modal-brands");
        if (!modal || !sidebar) return;
        modal.querySelectorAll(".js-modal-brand").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="brand"][value="' + cb.value + '"]'
            );
            if (side) side.checked = cb.checked;
        });
        closeFilterModal("brands");
        triggerCatalogFilterUpdate();
    }

    function applyNotesModal() {
        var modal = document.getElementById("filter-modal-notes");
        if (!modal || !sidebar) return;
        modal.querySelectorAll(".js-modal-note").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="notes"][value="' + cb.value + '"]'
            );
            if (side) side.checked = cb.checked;
        });
        closeFilterModal("notes");
        triggerCatalogFilterUpdate();
    }

    function triggerCatalogFilterUpdate() {
        var form = document.getElementById("catalog-form");
        if (!form || !sidebar) return;
        var el = sidebar.querySelector(
            'input[name="brand"], input[name="notes"], input[name="category"]'
        );
        if (el) {
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    document.body.addEventListener("click", function (e) {
        var openBtn = e.target.closest("[data-filter-modal-open]");
        if (openBtn) {
            e.preventDefault();
            openFilterModal(openBtn.getAttribute("data-filter-modal-open"));
            return;
        }
        var closeBtn = e.target.closest("[data-filter-modal-close]");
        if (closeBtn) {
            e.preventDefault();
            closeFilterModal(closeBtn.getAttribute("data-filter-modal-close"));
            return;
        }
        var applyBtn = e.target.closest("[data-filter-modal-apply]");
        if (applyBtn) {
            e.preventDefault();
            var w = applyBtn.getAttribute("data-filter-modal-apply");
            if (w === "brands") applyBrandsModal();
            else if (w === "notes") applyNotesModal();
        }
    });

    document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        if (!document.querySelector(".filter-modal.is-open")) return;
        closeAllFilterModals();
    });
})();
