"""
Server synthesis — synthesis transform run/regen/exit + status display.
"""
import asyncio
import traceback

import pandas as pd
from shiny import render, ui, reactive

from .context import ServerContext


def register_synthesis(ctx: ServerContext):
    """Register synthesis-related reactive effects and render outputs."""
    input = ctx.input
    config = ctx.config
    app_config = ctx.app_config
    data = ctx.data
    total_rows = ctx.total_rows
    filtered_row_count = ctx.filtered_row_count
    active_columns = ctx.active_columns
    current_page = ctx.current_page
    _table_reload_trigger = ctx._table_reload_trigger
    is_lazy_loading = ctx.is_lazy_loading
    load_data_from_source = ctx.load_data_from_source

    synthesis_active = ctx.synthesis_active
    synthesis_running = ctx.synthesis_running
    synthesis_data = ctx.synthesis_data
    synthesis_error = ctx.synthesis_error
    synthesis_cached = ctx.synthesis_cached
    enable_synthesis = ctx.enable_synthesis

    _initial_lazy_loading = ctx._initial_lazy_loading
    _synthesis_needs_generate = ctx._synthesis_needs_generate
    _synthesis_auto_triggered = {"done": False}

    # ── Auto-generate on startup ────────────────────────────────────────

    @reactive.Effect
    async def _auto_generate_synthesis():
        """Trigger synthesis generation automatically when cache is stale."""
        if _synthesis_auto_triggered["done"] or not _synthesis_needs_generate:
            return
        _synthesis_auto_triggered["done"] = True
        synthesis_running.set(True)
        synthesis_error.set("")
        try:
            result_df, was_cached = await asyncio.to_thread(config.run_synthesis)
            synthesis_data.set(result_df)
            synthesis_cached.set(was_cached)
            synthesis_active.set(True)
            data.set(result_df)
            total_rows.set(len(result_df))
            filtered_row_count.set(len(result_df))
            current_page.set(1)
            config.activate_synthesis_fetcher(config.get_synthesis_table_name())
            if config.all_columns:
                active_columns.set(list(config.all_columns))
            cache_msg = " (cached)" if was_cached else ""
            print(f"[Synthesis] Auto-generated{cache_msg} — {len(result_df):,} rows")
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            ui.notification_show(
                f"Synthesis ready{cache_msg} — {len(result_df):,} rows",
                type="message", duration=4
            )
        except Exception as e:
            traceback.print_exc()
            synthesis_error.set(str(e))
            ui.notification_show(
                f"Synthesis auto-generation failed: {e}",
                type="error", duration=6
            )
        finally:
            synthesis_running.set(False)

    # ── UI outputs ──────────────────────────────────────────────────────

    @render.ui
    def synthesis_query_preview():
        """Render the synthesis SQL query as a read-only code block."""
        if not enable_synthesis:
            return ui.div()
        query_text = app_config.synthesis.query or "(no query configured)"
        return ui.tags.pre(
            ui.tags.code(query_text),
            class_="synthesis-query-code"
        )

    @render.ui
    def synthesis_mode_banner():
        """Show a banner when the user is viewing synthesized data."""
        if not synthesis_active.get():
            return ui.div()
        label = app_config.synthesis.label or "Synthesis"
        return ui.div(
            ui.tags.i(class_="fa fa-flask", style="margin-right: 6px;"),
            f"You are viewing the {label} result table. ",
            "Filters and search operate on the synthesized data. ",
            "Click \"Exit Synthesis Mode\" to return to the original table.",
            class_="synthesis-mode-banner"
        )

    @render.ui
    def synthesis_status():
        """Show progress / error / success status inside the modal."""
        if synthesis_running.get():
            return ui.div(
                ui.div(class_="synthesis-spinner"),
                ui.p("Synthesizing report, please wait…",
                     style="margin-top: 10px; font-weight: 500;"),
                ui.p("This may take 3–5 minutes.",
                     style="color: #666; font-size: 13px;"),
                class_="synthesis-status-area"
            )
        err = synthesis_error.get()
        if err:
            return ui.div(
                ui.p("Transform failed:", style="color: #dc3545; font-weight: 600;"),
                ui.tags.pre(err, style="color: #dc3545; font-size: 12px; white-space: pre-wrap;"),
                class_="synthesis-status-area"
            )
        if synthesis_active.get():
            synth_df = synthesis_data.get()
            was_cached = synthesis_cached.get()
            cache_note = " (served from cache)" if was_cached else " (freshly generated)"
            ttl = app_config.synthesis.ttl_minutes
            countdown_html = ""
            try:
                import time as _srv_time
                cache_epoch = config._synthesis_age_cache_time
                if cache_epoch <= 0:
                    age_min = config._get_synthesis_age_minutes()
                    if age_min is not None:
                        cache_epoch = _srv_time.time() - age_min * 60
                    else:
                        cache_epoch = _srv_time.time()
                countdown_html = f"""
                <p style="color: #555; font-size: 13px; margin-top: 4px;">
                  <i class="fa fa-clock-o" style="margin-right: 5px;"></i>
                  <span id="synthesis-countdown"></span>
                </p>
                <script>
                (function() {{
                  var created = {cache_epoch:.3f};
                  var ttl = {ttl};
                  var el = document.getElementById('synthesis-countdown');
                  if (!el) return;
                  function fmt(sec) {{
                    sec = Math.max(0, Math.round(sec));
                    if (sec < 60) return sec + 's';
                    var m = Math.floor(sec / 60), s = sec % 60;
                    return m + 'm ' + (s < 10 ? '0' : '') + s + 's';
                  }}
                  function tick() {{
                    var age = Date.now() / 1000 - created;
                    var parts = ['Cache age: ' + fmt(age)];
                    if (ttl > 0) {{
                      var rem = ttl * 60 - age;
                      parts.push(rem > 0 ? 'expires in ' + fmt(rem) : 'expired');
                    }}
                    el.textContent = parts.join(' \\u00b7 ');
                  }}
                  tick();
                  var iv = setInterval(tick, 1000);
                  var obs = new MutationObserver(function() {{
                    if (!document.getElementById('synthesis-countdown')) {{
                      clearInterval(iv); obs.disconnect();
                    }}
                  }});
                  obs.observe(el.parentNode.parentNode, {{ childList: true, subtree: true }});
                }})();
                </script>
                """
            except Exception as _ce:
                print(f"[Synthesis] Countdown error: {_ce}")
            status_children = [
                ui.p("Transform complete", ui.tags.br(),
                     f"{len(synth_df):,} rows returned{cache_note}.",
                     style="color: #28a745; font-weight: 500;"),
            ]
            if countdown_html:
                status_children.append(ui.HTML(countdown_html))
            status_children.append(
                ui.p("Close this modal to interact with the synthesized table.",
                     style="color: #666; font-size: 13px;")
            )
            status_children.append(ui.HTML("""<script>
              (function(){
                var r=document.querySelector('[id$="synthesis_run_btn"]');
                var g=document.querySelector('[id$="synthesis_regen_btn"]');
                if(r) r.style.display='none';
                if(g) g.style.display='';
              })();
            </script>"""))
            return ui.div(*status_children, class_="synthesis-status-area")

        # Not active
        _btn_reset = ui.HTML("""<script>
          (function(){
            var r=document.querySelector('[id$="synthesis_run_btn"]');
            var g=document.querySelector('[id$="synthesis_regen_btn"]');
            if(r) r.style.display='';
            if(g) g.style.display='none';
          })();
        </script>""")
        if enable_synthesis:
            try:
                table_exists = config.check_synthesis_table_exists()
                ttl = app_config.synthesis.ttl_minutes
                if table_exists:
                    age = config._get_synthesis_age_minutes()
                    if age is not None:
                        age_text = f"{age:.0f} min" if age >= 1 else f"{age * 60:.0f}s"
                        ttl_text = f"TTL: {ttl} min." if ttl > 0 else ""
                        return ui.div(
                            _btn_reset,
                            ui.p(
                                ui.tags.i(class_="fa fa-database", style="margin-right: 6px; color: #28a745;"),
                                f"Cached result available — {age_text} old. {ttl_text}",
                                style="color: #28a745; font-size: 13px; font-weight: 500;"
                            ),
                            ui.p(
                                'Click "Run Transform" to load the cached table instantly.',
                                style="color: #666; font-size: 13px;"
                            ),
                            class_="synthesis-status-area"
                        )
                    else:
                        return ui.div(
                            _btn_reset,
                            ui.p(
                                ui.tags.i(class_="fa fa-database", style="margin-right: 6px; color: #17a2b8;"),
                                "Cached result table exists.",
                                style="color: #17a2b8; font-size: 13px; font-weight: 500;"
                            ),
                            ui.p(
                                'Click "Run Transform" to load it.',
                                style="color: #666; font-size: 13px;"
                            ),
                            class_="synthesis-status-area"
                        )
                else:
                    ttl_note = f" Result will be cached for {ttl} min." if ttl > 0 else ""
                    return ui.div(
                        _btn_reset,
                        ui.p(
                            ui.tags.i(class_="fa fa-info-circle", style="margin-right: 6px; color: #6c757d;"),
                            "No cached result.",
                            style="color: #6c757d; font-size: 13px; font-weight: 500;"
                        ),
                        ui.p(
                            f'Click "Run Transform" to execute the synthesis query and create the matview.{ttl_note}',
                            style="color: #666; font-size: 13px;"
                        ),
                        class_="synthesis-status-area"
                    )
            except Exception:
                pass
        return ui.div()

    # ── Run / Regen / Exit ──────────────────────────────────────────────

    @reactive.Effect
    @reactive.event(input.synthesis_run_btn)
    async def _run_synthesis():
        """Execute the synthesis transform."""
        if not enable_synthesis:
            return
        synthesis_running.set(True)
        synthesis_error.set("")
        try:
            result_df, was_cached = await asyncio.to_thread(config.run_synthesis)
            synthesis_data.set(result_df)
            synthesis_cached.set(was_cached)
            synthesis_active.set(True)
            data.set(result_df)
            total_rows.set(len(result_df))
            filtered_row_count.set(len(result_df))
            current_page.set(1)
            config.activate_synthesis_fetcher(config.get_synthesis_table_name())
            if config.all_columns:
                active_columns.set(list(config.all_columns))
            cache_msg = " (cached)" if was_cached else ""
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            ui.notification_show(
                f"Synthesis complete{cache_msg} — {len(result_df):,} rows",
                type="message", duration=4
            )
        except Exception as e:
            traceback.print_exc()
            synthesis_error.set(str(e))
        finally:
            synthesis_running.set(False)

    @reactive.Effect
    @reactive.event(input.synthesis_regen_btn)
    async def _regen_synthesis():
        """Force-recreate the synthesis view."""
        if not enable_synthesis:
            return
        synthesis_running.set(True)
        synthesis_error.set("")
        try:
            result_df, _ = await asyncio.to_thread(config.run_synthesis, force=True)
            synthesis_data.set(result_df)
            synthesis_cached.set(False)
            synthesis_active.set(True)
            data.set(result_df)
            total_rows.set(len(result_df))
            filtered_row_count.set(len(result_df))
            current_page.set(1)
            config.activate_synthesis_fetcher(config.get_synthesis_table_name())
            if config.all_columns:
                active_columns.set(list(config.all_columns))
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            ui.notification_show(
                f"Synthesis regenerated — {len(result_df):,} rows",
                type="message", duration=4
            )
        except Exception as e:
            traceback.print_exc()
            synthesis_error.set(str(e))
        finally:
            synthesis_running.set(False)

    @reactive.Effect
    @reactive.event(input.synthesis_exit_btn)
    def _exit_synthesis():
        """Exit synthesis mode and restore the original data table."""
        synthesis_active.set(False)
        synthesis_data.set(pd.DataFrame())
        synthesis_error.set("")
        config.deactivate_synthesis_fetcher()
        if _initial_lazy_loading:
            data.set(config.df)
            total_rows.set(config.total_row_count)
            filtered_row_count.set(config.total_row_count)
        else:
            fresh = load_data_from_source() if app_config.database.enabled else pd.DataFrame()
            data.set(fresh)
            total_rows.set(len(fresh))
            filtered_row_count.set(len(fresh))
        current_page.set(1)
        ui.notification_show("Returned to original table", type="message", duration=3)
