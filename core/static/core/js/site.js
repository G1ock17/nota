(function () {
    var searchRoots = document.querySelectorAll("[data-nav-search]");
    if (searchRoots.length) {
        var DEBOUNCE_MS = 240;
        var MIN_QUERY = 2;

        function formatSuggestPrice(minPriceStr) {
            if (minPriceStr == null || minPriceStr === "") return "нет в наличии";
            var n = parseFloat(String(minPriceStr), 10);
            if (isNaN(n)) return "нет в наличии";
            return "от " + n.toFixed(2).replace(".", ",") + " \u20BD";
        }

        function productHref(template, slug) {
            return String(template).split("__slug__").join(encodeURIComponent(slug));
        }

        function getNavSearchPanel(root) {
            return root._navSearchPanel || null;
        }

        function syncNavSearchPanelGeometry(root) {
            var input = root.querySelector(".nav-search__input");
            var panel = getNavSearchPanel(root);
            if (!input || !panel || !panel.classList.contains("is-open")) return;
            var r = input.getBoundingClientRect();
            var gap = 4;
            var margin = 10;
            var minPanel = 420;
            var maxPanel = Math.min(520, window.innerWidth - 2 * margin);
            var w = Math.min(Math.max(r.width, minPanel), maxPanel);
            var left = r.left;
            if (left + w > window.innerWidth - margin) {
                left = Math.max(margin, window.innerWidth - margin - w);
            }
            left = Math.max(margin, left);
            panel.style.left = left + "px";
            panel.style.top = r.bottom + gap + "px";
            panel.style.width = w + "px";
            var avail = window.innerHeight - r.bottom - gap - margin;
            var cap = 360;
            panel.style.maxHeight = Math.max(120, Math.min(cap, avail)) + "px";
        }

        function detachNavSearchPanelViewport(root) {
            if (!root._navSearchOnViewportChange) return;
            window.removeEventListener("scroll", root._navSearchOnViewportChange, true);
            window.removeEventListener("resize", root._navSearchOnViewportChange);
            root._navSearchOnViewportChange = null;
        }

        function closeSearchPanel(root) {
            detachNavSearchPanelViewport(root);
            var panel = getNavSearchPanel(root);
            var input = root.querySelector(".nav-search__input");
            if (!panel) return;
            panel.classList.remove("is-open");
            panel.innerHTML = "";
            panel.setAttribute("hidden", "");
            panel.style.left = "";
            panel.style.top = "";
            panel.style.width = "";
            panel.style.maxHeight = "";
            if (input) input.setAttribute("aria-expanded", "false");
        }

        function openSearchPanel(root, html) {
            var panel = getNavSearchPanel(root);
            var input = root.querySelector(".nav-search__input");
            if (!panel) return;
            panel.innerHTML = html;
            panel.removeAttribute("hidden");
            panel.classList.add("is-open");
            if (input) input.setAttribute("aria-expanded", "true");
            syncNavSearchPanelGeometry(root);
            if (!root._navSearchOnViewportChange) {
                root._navSearchOnViewportChange = function () {
                    syncNavSearchPanelGeometry(root);
                };
                window.addEventListener("scroll", root._navSearchOnViewportChange, true);
                window.addEventListener("resize", root._navSearchOnViewportChange);
            }
        }

        function renderResults(root, items, detailTpl) {
            if (!items.length) {
                openSearchPanel(
                    root,
                    '<p class="nav-search__hint">Ничего не найдено</p>'
                );
                return;
            }
            var frag = document.createDocumentFragment();
            items.forEach(function (item) {
                var href = productHref(detailTpl, item.slug);
                var a = document.createElement("a");
                a.href = href;
                a.className = "nav-search__row";

                if (item.image_url) {
                    var img = document.createElement("img");
                    img.src = item.image_url;
                    img.alt = "";
                    img.className = "nav-search__thumb";
                    img.width = 64;
                    img.height = 64;
                    img.loading = "lazy";
                    a.appendChild(img);
                } else {
                    var ph = document.createElement("span");
                    ph.className = "nav-search__thumb nav-search__thumb--empty";
                    ph.setAttribute("aria-hidden", "true");
                    ph.textContent = "—";
                    a.appendChild(ph);
                }

                var meta = document.createElement("div");
                meta.className = "nav-search__meta";

                var brand = document.createElement("div");
                brand.className = "nav-search__brand";
                brand.textContent = item.brand || "";
                meta.appendChild(brand);

                var name = document.createElement("p");
                name.className = "nav-search__name";
                name.textContent = item.name || "";
                meta.appendChild(name);

                a.appendChild(meta);

                var price = document.createElement("div");
                price.className = "nav-search__price";
                price.textContent = formatSuggestPrice(item.min_price);
                a.appendChild(price);

                frag.appendChild(a);
            });

            var wrap = document.createElement("div");
            wrap.appendChild(frag);
            openSearchPanel(root, wrap.innerHTML);
        }

        searchRoots.forEach(function (root) {
            var panelEl = root.querySelector("[data-nav-search-panel]");
            var input = root.querySelector(".nav-search__input");
            var urlBase = root.getAttribute("data-search-url") || "";
            var detailTpl = root.getAttribute("data-product-detail-template") || "";
            if (!input || !urlBase || !detailTpl || !panelEl) return;
            if (panelEl.parentElement !== document.body) {
                document.body.appendChild(panelEl);
            }
            root._navSearchPanel = panelEl;

            var debounceId = null;
            var abortCtl = null;

            function scheduleFetch(q) {
                if (debounceId) window.clearTimeout(debounceId);
                debounceId = window.setTimeout(function () {
                    debounceId = null;
                    runFetch(q);
                }, DEBOUNCE_MS);
            }

            function runFetch(q) {
                if (abortCtl) abortCtl.abort();
                if (q.length < MIN_QUERY) {
                    closeSearchPanel(root);
                    return;
                }
                abortCtl = new AbortController();
                var u = urlBase + (urlBase.indexOf("?") === -1 ? "?" : "&") + "q=" + encodeURIComponent(q);
                fetch(u, {
                    signal: abortCtl.signal,
                    headers: { Accept: "application/json" },
                    credentials: "same-origin",
                })
                    .then(function (r) {
                        if (!r.ok) throw new Error("search");
                        return r.json();
                    })
                    .then(function (data) {
                        var items = (data && data.results) || [];
                        renderResults(root, items, detailTpl);
                    })
                    .catch(function (err) {
                        if (err && err.name === "AbortError") return;
                        closeSearchPanel(root);
                    });
            }

            input.addEventListener("input", function () {
                var q = (input.value || "").trim();
                if (q.length < MIN_QUERY) {
                    if (debounceId) window.clearTimeout(debounceId);
                    if (abortCtl) abortCtl.abort();
                    closeSearchPanel(root);
                    return;
                }
                scheduleFetch(q);
            });

            input.addEventListener("focus", function () {
                var q = (input.value || "").trim();
                if (q.length >= MIN_QUERY) scheduleFetch(q);
            });

            input.addEventListener("keydown", function (e) {
                if (e.key === "Escape") {
                    closeSearchPanel(root);
                    input.blur();
                    root.classList.remove("nav-search--drawer-open");
                    document.querySelectorAll("[data-nav-search-mobile-trigger]").forEach(function (b) {
                        b.setAttribute("aria-expanded", "false");
                    });
                }
            });
        });

        function positionMobileNavSearchDrawer(root) {
            if (!window.matchMedia("(max-width: 1023px)").matches) {
                root.style.top = "";
                return;
            }
            var header = document.querySelector(".site-header");
            if (!header) return;
            root.style.top = Math.round(Math.max(0, header.getBoundingClientRect().bottom)) + "px";
        }

        document.querySelectorAll("[data-nav-search-mobile-trigger]").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                var root = document.querySelector("[data-nav-search]");
                var input = root && root.querySelector(".nav-search__input");
                if (!root || !input) return;
                var open = !root.classList.contains("nav-search--drawer-open");
                root.classList.toggle("nav-search--drawer-open", open);
                document.querySelectorAll("[data-nav-search-mobile-trigger]").forEach(function (b) {
                    b.setAttribute("aria-expanded", open ? "true" : "false");
                });
                if (open) {
                    positionMobileNavSearchDrawer(root);
                    window.requestAnimationFrame(function () {
                        input.focus();
                        syncNavSearchPanelGeometry(root);
                    });
                } else {
                    closeSearchPanel(root);
                    input.blur();
                }
            });
        });

        window.addEventListener(
            "resize",
            function () {
                searchRoots.forEach(function (root) {
                    if (root.classList.contains("nav-search--drawer-open")) {
                        positionMobileNavSearchDrawer(root);
                        syncNavSearchPanelGeometry(root);
                    } else {
                        root.style.top = "";
                    }
                });
            },
            { passive: true }
        );

        window.addEventListener(
            "scroll",
            function () {
                searchRoots.forEach(function (root) {
                    if (root.classList.contains("nav-search--drawer-open")) {
                        positionMobileNavSearchDrawer(root);
                        syncNavSearchPanelGeometry(root);
                    }
                });
            },
            true
        );

        document.addEventListener("click", function (e) {
            var t = e.target;
            searchRoots.forEach(function (root) {
                var p = getNavSearchPanel(root);
                var mobileTrig = t.closest && t.closest("[data-nav-search-mobile-trigger]");
                if (root.contains(t) || (p && p.contains(t)) || mobileTrig) return;
                closeSearchPanel(root);
                if (window.matchMedia("(max-width: 1023px)").matches) {
                    root.classList.remove("nav-search--drawer-open");
                    document.querySelectorAll("[data-nav-search-mobile-trigger]").forEach(function (b) {
                        b.setAttribute("aria-expanded", "false");
                    });
                }
            });
        });

        document.addEventListener("focusin", function (e) {
            var t = e.target;
            searchRoots.forEach(function (root) {
                var p = getNavSearchPanel(root);
                var mobileTrig = t.closest && t.closest("[data-nav-search-mobile-trigger]");
                if (root.contains(t) || (p && p.contains(t)) || mobileTrig) return;
                closeSearchPanel(root);
                if (window.matchMedia("(max-width: 1023px)").matches) {
                    root.classList.remove("nav-search--drawer-open");
                    document.querySelectorAll("[data-nav-search-mobile-trigger]").forEach(function (b) {
                        b.setAttribute("aria-expanded", "false");
                    });
                }
            });
        });
    }

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

    var revealObserver = new IntersectionObserver(
        function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    revealObserver.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.16 }
    );

    function observeRevealElements(nodeList) {
        nodeList.forEach(function (item) {
            revealObserver.observe(item);
        });
    }

    observeRevealElements(document.querySelectorAll(".reveal"));

    function scheduleCartToastAutoHide() {
        var toastEl = document.getElementById("cart-toast");
        if (!toastEl) return;
        window.clearTimeout(toastEl._toastHide);
        var msHint = toastEl.querySelector("[data-toast-autohide-ms]");
        var hideMs = msHint
            ? parseInt(msHint.getAttribute("data-toast-autohide-ms"), 10) || 5000
            : 4500;
        toastEl._toastHide = window.setTimeout(function () {
            var live = document.getElementById("cart-toast");
            if (live) live.innerHTML = "";
        }, hideMs);
    }

    document.body.addEventListener("htmx:afterSwap", function (e) {
        var t = e.detail && e.detail.target;
        if (t && t.id === "catalog-results") {
            observeRevealElements(t.querySelectorAll(".reveal"));
        }
        if (t && t.id === "catalog-product-grid") {
            observeRevealElements(t.querySelectorAll(".reveal"));
        }
        if (t && t.id === "cart-toast") {
            scheduleCartToastAutoHide();
        }
    });

    document.body.addEventListener("htmx:oobAfterSwap", function (e) {
        var d = e.detail || {};
        if (!d.target || d.target.id !== "cart-toast") return;
        window.requestAnimationFrame(function () {
            scheduleCartToastAutoHide();
        });
    });

    document.querySelectorAll("[data-product-gallery]").forEach(function (gallery) {
        var main = gallery.querySelector("[data-gallery-main]");
        var thumbs = gallery.querySelectorAll("[data-gallery-thumb]");
        if (!main) return;

        if (thumbs.length) {
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
        }

        var lightbox = gallery.querySelector("[data-product-image-lightbox]");
        var lightboxImg = gallery.querySelector("[data-product-image-lightbox-img]");
        var trigger = gallery.querySelector("[data-gallery-lightbox-trigger]");
        var lbPrev = lightbox ? lightbox.querySelector("[data-lightbox-prev]") : null;
        var lbNext = lightbox ? lightbox.querySelector("[data-lightbox-next]") : null;
        var lbThumbBtns = lightbox ? lightbox.querySelectorAll("[data-lightbox-slide-thumb]") : [];
        if (!lightbox || !lightboxImg || !trigger) return;

        var prevOverflow = "";
        var lbSlides = [];
        var lbIndex = 0;

        function lbBuildSlides() {
            lbSlides = [];
            if (lbThumbBtns.length) {
                lbThumbBtns.forEach(function (btn) {
                    var u = btn.getAttribute("data-image-url");
                    if (u) {
                        lbSlides.push({
                            src: u,
                            alt: btn.getAttribute("data-image-alt") || ""
                        });
                    }
                });
            } else {
                var s = main.getAttribute("src");
                if (s) {
                    lbSlides.push({ src: s, alt: main.getAttribute("alt") || "" });
                }
            }
        }

        function lbSyncMainFromLightbox() {
            var slide = lbSlides[lbIndex];
            if (!slide) return;
            main.setAttribute("src", slide.src);
            main.setAttribute("alt", slide.alt);
            gallery.querySelectorAll("[data-gallery-thumb]").forEach(function (t) {
                t.classList.toggle("is-active", t.getAttribute("data-image-url") === slide.src);
            });
        }

        function lbShowSlide(i) {
            lbBuildSlides();
            if (!lbSlides.length) return;
            lbIndex = Math.max(0, Math.min(lbSlides.length - 1, i));
            var slide = lbSlides[lbIndex];
            lightboxImg.setAttribute("src", slide.src);
            lightboxImg.setAttribute("alt", slide.alt);
            lbThumbBtns.forEach(function (btn, idx) {
                var on = idx === lbIndex;
                btn.classList.toggle("is-active", on);
                btn.setAttribute("aria-selected", on ? "true" : "false");
            });
            if (lbPrev) {
                lbPrev.disabled = lbIndex === 0;
            }
            if (lbNext) {
                lbNext.disabled = lbIndex >= lbSlides.length - 1;
            }
            if (lbSlides.length > 1) {
                lbSyncMainFromLightbox();
            }
        }

        var zoomWrap = lightbox.querySelector(".product-image-lightbox__zoom-wrap");
        var lbCloseAnimTimer = null;
        var lbCloseAnimHandler = null;

        function cancelLightboxCloseAnimation() {
            window.clearTimeout(lbCloseAnimTimer);
            lbCloseAnimTimer = null;
            if (lbCloseAnimHandler && zoomWrap) {
                zoomWrap.removeEventListener("transitionend", lbCloseAnimHandler);
            }
            lbCloseAnimHandler = null;
        }

        function finishCloseLightbox() {
            cancelLightboxCloseAnimation();
            lightbox.classList.remove("is-open", "is-closing");
            document.body.style.overflow = prevOverflow;
            lightboxImg.removeAttribute("src");
        }

        function openLightbox() {
            lbBuildSlides();
            if (!lbSlides.length) return;
            cancelLightboxCloseAnimation();
            lightbox.classList.remove("is-closing");
            var mainSrc = main.getAttribute("src");
            lbIndex = 0;
            for (var j = 0; j < lbSlides.length; j++) {
                if (lbSlides[j].src === mainSrc) {
                    lbIndex = j;
                    break;
                }
            }
            lbShowSlide(lbIndex);
            lightbox.classList.add("is-open");
            prevOverflow = document.body.style.overflow;
            document.body.style.overflow = "hidden";
            var closeBtn = lightbox.querySelector("[data-product-image-lightbox-close].product-image-lightbox__close");
            if (closeBtn) closeBtn.focus();
        }

        function closeLightbox() {
            if (!lightbox.classList.contains("is-open") || lightbox.classList.contains("is-closing")) return;
            if (zoomWrap) {
                var done = false;
                function runClose() {
                    if (done) return;
                    done = true;
                    cancelLightboxCloseAnimation();
                    finishCloseLightbox();
                }
                lbCloseAnimHandler = function (e) {
                    if (e.propertyName !== "transform") return;
                    runClose();
                };
                zoomWrap.addEventListener("transitionend", lbCloseAnimHandler);
                lbCloseAnimTimer = window.setTimeout(runClose, 520);
                lightbox.classList.add("is-closing");
                return;
            }
            finishCloseLightbox();
        }

        trigger.addEventListener("click", openLightbox);

        lightbox.querySelectorAll("[data-product-image-lightbox-close]").forEach(function (el) {
            el.addEventListener("click", function (e) {
                e.preventDefault();
                closeLightbox();
            });
        });

        document.addEventListener("keydown", function (e) {
            if (!lightbox.classList.contains("is-open")) return;
            if (e.key === "Escape") {
                closeLightbox();
                return;
            }
            if (e.key === "ArrowLeft" && lbPrev && !lbPrev.disabled) {
                e.preventDefault();
                lbShowSlide(lbIndex - 1);
            } else if (e.key === "ArrowRight" && lbNext && !lbNext.disabled) {
                e.preventDefault();
                lbShowSlide(lbIndex + 1);
            }
        });

        if (lbPrev) {
            lbPrev.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                lbShowSlide(lbIndex - 1);
            });
        }
        if (lbNext) {
            lbNext.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                lbShowSlide(lbIndex + 1);
            });
        }
        lbThumbBtns.forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                var raw = btn.getAttribute("data-slide-index");
                var idx = raw != null ? parseInt(raw, 10) : 0;
                if (!isNaN(idx)) {
                    lbShowSlide(idx);
                }
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
        var body = modal.querySelector(".filter-modal__body");
        var rows = body
            ? body.querySelectorAll(".js-modal-filter-row")
            : modal.querySelectorAll(".js-modal-filter-row");

        if (!q) {
            rows.forEach(function (row) {
                row.classList.remove("is-filter-match-hidden");
            });
            return;
        }

        rows.forEach(function (row) {
            var hay = modalFilterHaystack(row);
            var match = hay.indexOf(q) !== -1;
            row.classList.toggle("is-filter-match-hidden", !match);
        });
    }

    /**
     * В модалках фильтров поднимает отмеченные пункты вверх списка.
     * Вызывается только по кнопке «Применить», не при открытии модалки и не при переключении чекбокса.
     */
    function sortModalFilterRowsCheckedFirst(modal) {
        if (!modal) return;
        function reorderContainer(container, rows) {
            if (!container || !rows.length) return;
            var list = Array.prototype.slice.call(rows);
            list.sort(function (a, b) {
                var ia = a.querySelector('input[type="checkbox"]');
                var ib = b.querySelector('input[type="checkbox"]');
                var ca = ia && ia.checked;
                var cb = ib && ib.checked;
                if (ca === cb) return 0;
                return ca ? -1 : 1;
            });
            list.forEach(function (row) {
                container.appendChild(row);
            });
        }

        var body = modal.querySelector(".filter-modal__body");
        if (!body) return;
        var rows = body.querySelectorAll(".js-modal-filter-row");
        reorderContainer(body, rows);
    }

    function sidebarNotesInputByValue(value) {
        if (!sidebar || value == null) return null;
        var inputs = sidebar.querySelectorAll('input[name="notes"]');
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].value === value) return inputs[i];
        }
        return null;
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
            var side = sidebarNotesInputByValue(cb.value);
            cb.checked = !!(side && side.checked);
        });
    }

    function syncYearsModalFromSidebar() {
        var modal = document.getElementById("filter-modal-years");
        if (!modal || !sidebar) return;
        modal.querySelectorAll(".js-modal-year").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="year"][value="' + cb.value + '"]'
            );
            cb.checked = !!(side && side.checked);
        });
    }

    function syncCountriesModalFromSidebar() {
        var modal = document.getElementById("filter-modal-countries");
        if (!modal || !sidebar) return;
        modal.querySelectorAll(".js-modal-country").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="country"][value="' + cb.value + '"]'
            );
            cb.checked = !!(side && side.checked);
        });
    }

    function closeFilterModal(which) {
        var ids = {
            brands: "filter-modal-brands",
            notes: "filter-modal-notes",
            years: "filter-modal-years",
            countries: "filter-modal-countries",
        };
        var id = ids[which];
        var m = document.getElementById(id);
        if (!m) return;
        m.classList.remove("is-open");
        m.setAttribute("aria-hidden", "true");
        restoreCatalogPageScroll();
    }

    function closeAllFilterModals() {
        document.querySelectorAll(".filter-modal.is-open").forEach(function (m) {
            m.classList.remove("is-open");
            m.setAttribute("aria-hidden", "true");
        });
        restoreCatalogPageScroll();
    }

    function openFilterModal(which) {
        closeAllFilterModals();
        if (which === "brands") syncBrandsModalFromSidebar();
        else if (which === "notes") syncNotesModalFromSidebar();
        else if (which === "years") syncYearsModalFromSidebar();
        else if (which === "countries") syncCountriesModalFromSidebar();
        var ids = {
            brands: "filter-modal-brands",
            notes: "filter-modal-notes",
            years: "filter-modal-years",
            countries: "filter-modal-countries",
        };
        var id = ids[which];
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

    document.body.addEventListener("change", function (e) {
        var t = e.target;
        if (!t || t.type !== "checkbox") return;
        var modal = t.closest(".filter-modal");
        if (!modal || !modal.classList.contains("is-open")) return;
        if (!modal.querySelector(".js-modal-filter-row")) return;
        var searchInp = modal.querySelector(".filter-modal__search");
        if (searchInp && searchInp.value) {
            filterModalList(modal, searchInp.value);
        }
    });

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
        sortModalFilterRowsCheckedFirst(modal);
        modal.querySelectorAll(".js-modal-brand").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="brand"][value="' + cb.value + '"]'
            );
            if (side) side.checked = cb.checked;
        });
        updateCatalogFilterModalTriggerLabels();
        closeFilterModal("brands");
        triggerCatalogFilterUpdate();
    }

    function applyNotesModal() {
        var modal = document.getElementById("filter-modal-notes");
        if (!modal || !sidebar) return;
        sortModalFilterRowsCheckedFirst(modal);
        modal.querySelectorAll(".js-modal-note").forEach(function (cb) {
            var side = sidebarNotesInputByValue(cb.value);
            if (side) side.checked = cb.checked;
        });
        updateCatalogFilterModalTriggerLabels();
        closeFilterModal("notes");
        triggerCatalogFilterUpdate();
    }

    function applyYearsModal() {
        var modal = document.getElementById("filter-modal-years");
        if (!modal || !sidebar) return;
        sortModalFilterRowsCheckedFirst(modal);
        modal.querySelectorAll(".js-modal-year").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="year"][value="' + cb.value + '"]'
            );
            if (side) side.checked = cb.checked;
        });
        updateCatalogFilterModalTriggerLabels();
        closeFilterModal("years");
        triggerCatalogFilterUpdate();
    }

    function applyCountriesModal() {
        var modal = document.getElementById("filter-modal-countries");
        if (!modal || !sidebar) return;
        sortModalFilterRowsCheckedFirst(modal);
        modal.querySelectorAll(".js-modal-country").forEach(function (cb) {
            var side = sidebar.querySelector(
                'input[name="country"][value="' + cb.value + '"]'
            );
            if (side) side.checked = cb.checked;
        });
        updateCatalogFilterModalTriggerLabels();
        closeFilterModal("countries");
        triggerCatalogFilterUpdate();
    }

    function triggerCatalogFilterUpdate() {
        var form = document.getElementById("catalog-form");
        if (!form) return;
        if (typeof htmx !== "undefined" && typeof htmx.trigger === "function") {
            htmx.trigger(form, "catalog-filters-apply");
        } else {
            form.submit();
        }
    }

    /**
     * Подписи «Бренды (n)» на кнопках модалок: в #catalog-results они обновляются с сервера,
     * а копия в мобильном сайдбаре — нет; пересчитываем по чекбоксам формы для всех кнопок.
     */
    function updateCatalogFilterModalTriggerLabels() {
        var form = document.getElementById("catalog-form");
        if (!form) return;
        function countChecked(inputName) {
            return form.querySelectorAll('input[name="' + inputName + '"]:checked').length;
        }
        var counts = {
            brands: countChecked("brand"),
            notes: countChecked("notes"),
            years: countChecked("year"),
            countries: countChecked("country"),
        };
        var base = {
            brands: "Бренды",
            notes: "Ноты",
            years: "Год",
            countries: "Страна",
        };
        document.querySelectorAll("[data-filter-modal-open]").forEach(function (btn) {
            var w = btn.getAttribute("data-filter-modal-open");
            if (!w || base[w] == null) return;
            var n = counts[w];
            btn.textContent = n > 0 ? base[w] + " (" + n + ")" : base[w];
        });
    }

    /**
     * Сбрасывает только один тип фильтра (бренды / ноты / год / страна): модалка, скрытые поля сайдбара и каталог.
     * Остальные фильтры не трогаются.
     */
    function clearAllFilterModal(which) {
        if (!sidebar) return;
        var ids = {
            brands: "filter-modal-brands",
            notes: "filter-modal-notes",
            years: "filter-modal-years",
            countries: "filter-modal-countries",
        };
        var id = ids[which];
        if (!id) return;
        var m = document.getElementById(id);
        if (!m) return;

        var sidebarName;
        var modalSelector;
        if (which === "brands") {
            sidebarName = "brand";
            modalSelector = ".js-modal-brand";
        } else if (which === "notes") {
            sidebarName = "notes";
            modalSelector = ".js-modal-note";
        } else if (which === "years") {
            sidebarName = "year";
            modalSelector = ".js-modal-year";
        } else if (which === "countries") {
            sidebarName = "country";
            modalSelector = ".js-modal-country";
        } else {
            return;
        }

        m.querySelectorAll(modalSelector).forEach(function (cb) {
            cb.checked = false;
        });
        sidebar.querySelectorAll('input[name="' + sidebarName + '"]').forEach(function (cb) {
            cb.checked = false;
        });

        var searchInp = m.querySelector(".filter-modal__search");
        if (searchInp) {
            searchInp.value = "";
            filterModalList(m, "");
        }

        updateCatalogFilterModalTriggerLabels();
        closeFilterModal(which);
        triggerCatalogFilterUpdate();
    }

    function restoreCatalogPageScroll() {
        if (
            !document.querySelector(".filter-modal.is-open") &&
            !document.querySelector(".catalog-mobile-filters-aside.is-open")
        ) {
            document.body.style.overflow = "";
        }
    }

    function getCatalogMobileFiltersBackdrop() {
        return document.getElementById("catalog-mobile-filters-backdrop");
    }

    function catalogMobileFiltersOpen() {
        var aside = document.getElementById("catalog-sidebar-filters");
        var backdrop = getCatalogMobileFiltersBackdrop();
        if (!aside || !window.matchMedia("(max-width: 1023px)").matches) return;
        aside.classList.add("is-open");
        aside.setAttribute("aria-hidden", "false");
        if (backdrop) {
            backdrop.removeAttribute("hidden");
            backdrop.classList.add("is-active");
            backdrop.setAttribute("aria-hidden", "false");
        }
        document.body.classList.add("catalog-mobile-filters-open");
        document.body.style.overflow = "hidden";
        updateCatalogSortSelects();
    }

    function catalogMobileFiltersClose() {
        var aside = document.getElementById("catalog-sidebar-filters");
        var backdrop = getCatalogMobileFiltersBackdrop();
        if (!aside) return;
        aside.classList.remove("is-open");
        aside.setAttribute("aria-hidden", "true");
        if (backdrop) {
            backdrop.classList.remove("is-active");
            backdrop.setAttribute("hidden", "hidden");
            backdrop.setAttribute("aria-hidden", "true");
        }
        document.body.classList.remove("catalog-mobile-filters-open");
        if (window.matchMedia("(min-width: 1024px)").matches) {
            aside.removeAttribute("aria-hidden");
        } else {
            aside.setAttribute("aria-hidden", "true");
        }
        restoreCatalogPageScroll();
    }

    function updateCatalogSortSelects() {
        var mq = window.matchMedia("(max-width: 1023px)").matches;
        var desk = document.querySelector(".catalog-sort-bar-desktop-sort");
        var mob = document.querySelector(".catalog-sort-bar-mobile-sort");
        if (!desk && !mob) return;
        if (desk) desk.disabled = !!mq;
        if (mob) mob.disabled = !mq;
        if (mq && desk && mob) {
            mob.value = desk.value;
        } else if (!mq && desk && mob) {
            desk.value = mob.value;
        }
    }

    document.body.addEventListener("click", function (e) {
        var mOpen = e.target.closest("[data-catalog-mobile-filters-open]");
        if (mOpen) {
            e.preventDefault();
            catalogMobileFiltersOpen();
            return;
        }
        var mClose = e.target.closest("[data-catalog-mobile-filters-close]");
        if (mClose) {
            e.preventDefault();
            catalogMobileFiltersClose();
            return;
        }
        var openBtn = e.target.closest("[data-filter-modal-open]");
        if (openBtn) {
            e.preventDefault();
            openFilterModal(openBtn.getAttribute("data-filter-modal-open"));
            return;
        }
        var clearAllBtn = e.target.closest("[data-filter-modal-clear-all]");
        if (clearAllBtn) {
            e.preventDefault();
            clearAllFilterModal(clearAllBtn.getAttribute("data-filter-modal-clear-all"));
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
            else if (w === "years") applyYearsModal();
            else if (w === "countries") applyCountriesModal();
        }
    });

    document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        if (document.querySelector(".filter-modal.is-open")) {
            closeAllFilterModals();
            return;
        }
        var aside = document.querySelector(".catalog-mobile-filters-aside.is-open");
        if (aside) {
            catalogMobileFiltersClose();
        }
    });

    document.body.addEventListener("htmx:afterSwap", function (e) {
        var t = e.detail && e.detail.target;
        if (t && t.id === "catalog-results") {
            updateCatalogSortSelects();
            updateCatalogFilterModalTriggerLabels();
        }
    });

    window.addEventListener(
        "resize",
        function () {
            if (window.matchMedia("(min-width: 1024px)").matches) {
                catalogMobileFiltersClose();
            }
            updateCatalogSortSelects();
        },
        { passive: true }
    );

    updateCatalogSortSelects();
    (function initCatalogMobileAsideAria() {
        var aside = document.getElementById("catalog-sidebar-filters");
        if (!aside) return;
        if (window.matchMedia("(max-width: 1023px)").matches) {
            aside.setAttribute("aria-hidden", "true");
        }
    })();

    (function initNavBrandsMega() {
        var header = document.querySelector(".site-header");
        var trigger = header && header.querySelector("[data-nav-brands-trigger]");
        var panel = header && header.querySelector("[data-nav-brands-panel]");
        if (!header || !trigger || !panel) return;

        var closeTimer = null;
        var DELAY = 160;

        function syncAriaHidden() {
            var open =
                panel.classList.contains("is-open") ||
                (document.activeElement &&
                    (trigger.contains(document.activeElement) ||
                        panel.contains(document.activeElement)));
            panel.setAttribute("aria-hidden", open ? "false" : "true");
        }

        function openPanel() {
            clearTimeout(closeTimer);
            panel.classList.add("is-open");
            syncAriaHidden();
        }

        function scheduleClose() {
            clearTimeout(closeTimer);
            closeTimer = setTimeout(function () {
                panel.classList.remove("is-open");
                syncAriaHidden();
            }, DELAY);
        }

        function cancelClose() {
            clearTimeout(closeTimer);
        }

        trigger.addEventListener("mouseenter", function () {
            cancelClose();
            openPanel();
        });
        trigger.addEventListener("mouseleave", scheduleClose);
        panel.addEventListener("mouseenter", function () {
            cancelClose();
            openPanel();
        });
        panel.addEventListener("mouseleave", scheduleClose);

        var brandsLink = trigger.querySelector("a");

        function closeIfFocusLeft() {
            setTimeout(function () {
                var ae = document.activeElement;
                if (!trigger.contains(ae) && !panel.contains(ae)) {
                    panel.classList.remove("is-open");
                    syncAriaHidden();
                }
            }, 0);
        }

        /* Клавиатура: открывать по Tab, не открывать от клика мыши (без :focus-visible) */
        trigger.addEventListener("focusin", function () {
            requestAnimationFrame(function () {
                if (
                    brandsLink &&
                    document.activeElement === brandsLink &&
                    brandsLink.matches(":focus-visible")
                ) {
                    cancelClose();
                    openPanel();
                }
            });
        });
        panel.addEventListener("focusin", function () {
            cancelClose();
            openPanel();
        });
        trigger.addEventListener("focusout", function () {
            syncAriaHidden();
            closeIfFocusLeft();
        });
        panel.addEventListener("focusout", function () {
            syncAriaHidden();
            closeIfFocusLeft();
        });

        window.addEventListener(
            "resize",
            function () {
                if (!window.matchMedia("(min-width: 1024px)").matches) {
                    cancelClose();
                    panel.classList.remove("is-open");
                    syncAriaHidden();
                }
            },
            { passive: true }
        );
    })();

    (function initMobileHeaderScrollHide() {
        var header = document.querySelector(".site-header");
        var spacer = document.getElementById("site-header-mobile-spacer");
        if (!header || !spacer) return;

        var mq = window.matchMedia("(max-width: 1023px)");
        var lastScrollY = window.scrollY || 0;
        var headerVisible = true;
        var HEADER_HIDE_CLASS = "site-header--scroll-hidden";
        var T_TOP = 16;
        /* Накопление по направлению: медленный скролл и шум не дергают шапку.
           Спейсер всегда = высоте шапки — иначе схлопывание меняет scrollY и даёт «мигание». */
        var accumDown = 0;
        var accumUp = 0;
        var HIDE_AFTER = 56;
        var SHOW_AFTER = 40;
        var NOISE = 1.25;
        var ticking = false;

        function applyLayout() {
            ticking = false;
            if (!mq.matches) {
                spacer.style.height = "";
                document.documentElement.style.removeProperty("--site-header-offset");
                header.classList.remove(HEADER_HIDE_CLASS);
                return;
            }
            var h = header.offsetHeight;
            spacer.style.height = h + "px";
            if (headerVisible) {
                header.classList.remove(HEADER_HIDE_CLASS);
                document.documentElement.style.setProperty("--site-header-offset", h + "px");
            } else {
                header.classList.add(HEADER_HIDE_CLASS);
                document.documentElement.style.setProperty("--site-header-offset", "0px");
            }
        }

        function requestApply() {
            if (!ticking) {
                ticking = true;
                window.requestAnimationFrame(applyLayout);
            }
        }

        function onScroll() {
            if (!mq.matches) return;
            var y = window.scrollY || document.documentElement.scrollTop || 0;
            var delta = y - lastScrollY;
            lastScrollY = y;
            var changed = false;

            if (y <= T_TOP) {
                accumDown = 0;
                accumUp = 0;
                if (!headerVisible) {
                    headerVisible = true;
                    changed = true;
                }
            } else if (Math.abs(delta) < NOISE) {
                return;
            } else if (delta > 0) {
                accumDown += delta;
                accumUp = 0;
                if (accumDown >= HIDE_AFTER && headerVisible) {
                    headerVisible = false;
                    accumDown = 0;
                    changed = true;
                }
            } else {
                accumUp += -delta;
                accumDown = 0;
                if (accumUp >= SHOW_AFTER && !headerVisible) {
                    headerVisible = true;
                    accumUp = 0;
                    changed = true;
                }
            }

            if (changed) requestApply();
        }

        function onResizeOrMq() {
            lastScrollY = window.scrollY || 0;
            accumDown = 0;
            accumUp = 0;
            if (!mq.matches) {
                headerVisible = true;
            }
            applyLayout();
        }

        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onResizeOrMq, { passive: true });
        if (mq.addEventListener) {
            mq.addEventListener("change", onResizeOrMq);
        } else if (mq.addListener) {
            mq.addListener(onResizeOrMq);
        }
        onResizeOrMq();
    })();

    (function () {
        var modal = document.getElementById("favorite-auth-modal");
        if (!modal) return;

        var postAuthPath = modal.getAttribute("data-post-auth-path") || "";
        var loginPath = modal.getAttribute("data-login-path") || "";
        var registerPath = modal.getAttribute("data-register-path") || "";
        var loginLink = document.getElementById("favorite-auth-modal-login");
        var registerLink = document.getElementById("favorite-auth-modal-register");

        function currentReturnPath() {
            return window.location.pathname + window.location.search;
        }

        function buildPostAuthQuery(productId, returnPath) {
            var params = new URLSearchParams();
            params.set("product", String(productId));
            params.set("next", returnPath || "/products/");
            var q = params.toString();
            var sep = postAuthPath.indexOf("?") >= 0 ? "&" : "?";
            return postAuthPath + sep + q;
        }

        function syncLinks(productId) {
            if (!loginLink || !registerLink) return;
            var ret = currentReturnPath();
            var target = buildPostAuthQuery(productId, ret);
            loginLink.setAttribute("href", loginPath + "?next=" + encodeURIComponent(target));
            registerLink.setAttribute("href", registerPath + "?next=" + encodeURIComponent(target));
        }

        function openModal(productId) {
            syncLinks(productId);
            modal.classList.add("is-open");
            modal.setAttribute("aria-hidden", "false");
            document.documentElement.style.overflow = "hidden";
        }

        function closeModal() {
            modal.classList.remove("is-open");
            modal.setAttribute("aria-hidden", "true");
            document.documentElement.style.overflow = "";
        }

        document.addEventListener("click", function (e) {
            var t = e.target;
            if (!t || !t.closest) return;
            var opener = t.closest("[data-favorite-auth-modal-open]");
            if (opener) {
                e.preventDefault();
                var pid = opener.getAttribute("data-product-id");
                if (!pid) return;
                openModal(pid);
                return;
            }
            if (t.closest("[data-favorite-auth-modal-close]")) {
                closeModal();
            }
        });

        document.addEventListener("keydown", function (e) {
            if (e.key !== "Escape") return;
            if (!modal.classList.contains("is-open")) return;
            closeModal();
        });
    })();
})();
