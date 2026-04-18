/* Javascript for TASXBlock Studio Edit */
function TASXBlockInitEdit(runtime, element) {

    var $el = $(element);

    // ── SVG icons ─────────────────────────────────────────────────────────────

    function escAttr(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    var CHEVRON_SVG =
        '<svg viewBox="0 0 20 20" fill="currentColor">' +
        '<path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>' +
        '</svg>';

    var TRASH_SVG =
        '<svg viewBox="0 0 20 20" fill="currentColor">' +
        '<path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/>' +
        '</svg>';

    var PLUS_SVG =
        '<svg viewBox="0 0 20 20" fill="currentColor">' +
        '<path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd"/>' +
        '</svg>';

    var WARN_SVG =
        '<svg viewBox="0 0 20 20" fill="currentColor">' +
        '<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>' +
        '</svg>';

    // ── Empty-state & badge ───────────────────────────────────────────────────

    function updateEmptyState() {
        var count = $el.find('.criterion-block').length;
        $el.find('.te-empty-state').toggleClass('visible', count === 0);
        var $badge = $el.find('.te-rubric-count');
        count > 0 ? $badge.text(count).show() : $badge.hide();
    }

    function renumberCriteria() {
        $el.find('.criterion-block').each(function(i) {
            $(this).find('.criterion-num').text(i + 1);
        });
    }

    // ── Validation ────────────────────────────────────────────────────────────

    function clearErrors() {
        $el.find('.te-validation-banner').remove();
        $el.find('.te-field-error').remove();
        $el.find('.te-input-error').removeClass('te-input-error');
        $el.find('.criterion-block.te-has-error').removeClass('te-has-error');
        $el.find('.option-row.te-has-error').removeClass('te-has-error');
    }

    function showBanner(msg) {
        var $banner = $(
            '<div class="te-validation-banner">' + WARN_SVG + escAttr(msg) + '</div>'
        );
        $el.find('.te-tabs').after($banner);
    }

    function addInputError($input, msg) {
        $input.addClass('te-input-error');
        if (msg) {
            $input.after('<span class="te-field-error">' + escAttr(msg) + '</span>');
        }
    }

    function validate() {
        clearErrors();
        var valid = true;
        var rubricErrors = false;

        // Display Name
        if (!$el.find('#tas_edit_display_name').val().trim()) {
            addInputError($el.find('#tas_edit_display_name'), 'Display name is required.');
            valid = false;
            // Switch to settings tab to reveal the error
            $el.find('.te-tab[data-tab="settings"]').trigger('click');
        }

        // Criteria
        $el.find('.criterion-block').each(function() {
            var $block = $(this);
            var $nameInput = $block.find('.criterion-name');
            var criterionOk = true;

            if (!$nameInput.val().trim()) {
                $block.addClass('te-has-error');
                // Expand collapsed block so error is visible
                $block.removeClass('collapsed');
                addInputError($nameInput, 'Criterion name is required.');
                valid = false;
                rubricErrors = true;
                criterionOk = false;
            }

            $block.find('.option-row').each(function() {
                var $row = $(this);
                var $optName = $row.find('.opt-name');
                if (!$optName.val().trim()) {
                    $row.addClass('te-has-error');
                    addInputError($optName, 'Option name is required.');
                    valid = false;
                    rubricErrors = true;
                }
            });
        });

        if (!valid) {
            showBanner('Please fix the errors below before saving.');
            // If rubric errors exist, switch to rubrics tab (unless settings also errored first)
            if (rubricErrors && $el.find('#tas_edit_display_name').val().trim()) {
                $el.find('.te-tab[data-tab="rubrics"]').trigger('click');
            }
        }

        return valid;
    }

    // ── Option rows ──────────────────────────────────────────────────────────

    function buildOptionRow(name, marks, description) {
        name        = name        || '';
        marks       = (marks !== undefined && marks !== null) ? marks : '';
        description = description || '';

        return $(
            '<div class="option-row">' +
                '<input type="text" class="opt-input opt-name" placeholder="Option name"  value="' + escAttr(name)          + '">' +
                '<input type="text" class="opt-input opt-desc" placeholder="Description"  value="' + escAttr(description)   + '">' +
                '<input type="text" class="opt-marks"          placeholder="0"            value="' + escAttr(String(marks)) + '">' +
                '<button type="button" class="del-option" title="Remove option">' + TRASH_SVG + '</button>' +
            '</div>'
        );
    }

    // ── Criterion blocks ─────────────────────────────────────────────────────

    function buildCriterionBlock(criterion, options) {
        criterion = criterion || '';
        options   = options   || [];

        var index = $el.find('.criterion-block').length + 1;

        var $block = $(
            '<div class="criterion-block">' +
                '<div class="criterion-header">' +
                    '<span class="criterion-num">' + index + '</span>' +
                    '<input type="text" class="criterion-name" placeholder="Criterion name…" value="' + escAttr(criterion) + '">' +
                    '<button type="button" class="criterion-toggle" title="Collapse/Expand">' + CHEVRON_SVG + '</button>' +
                    '<button type="button" class="del-criterion" title="Remove criterion">' + TRASH_SVG + ' Remove</button>' +
                '</div>' +
                '<div class="criterion-body">' +
                    '<div class="options-header-row">' +
                        '<span>Option Name</span>' +
                        '<span>Description</span>' +
                        '<span style="text-align:center">Marks</span>' +
                        '<span></span>' +
                    '</div>' +
                    '<div class="option-rows"></div>' +
                    '<button type="button" class="add-option">' + PLUS_SVG + ' Add Option</button>' +
                '</div>' +
            '</div>'
        );

        var $optRows = $block.find('.option-rows');
        options.forEach(function(opt) {
            $optRows.append(buildOptionRow(opt.name, opt.marks, opt.description));
        });

        return $block;
    }

    function addCriterion(criterion, options) {
        var $block = buildCriterionBlock(criterion, options);
        $el.find('.criteria-list').append($block);
        updateEmptyState();
        $block.hide().slideDown(180);
    }

    // ── Load existing rubrics ─────────────────────────────────────────────────
    // element may be a Studio wrapper around .tas-editor, not .tas-editor itself.
    // Check both the element and its descendant for data-rubrics.

    var $rubricSource = $el.is('[data-rubrics]') ? $el : $el.find('[data-rubrics]').first();
    var dataRubrics = $rubricSource.attr('data-rubrics');
    if (dataRubrics && dataRubrics !== '[]') {
        try {
            JSON.parse(dataRubrics).forEach(function(r) {
                var $block = buildCriterionBlock(r.criterion, r.options || []);
                $el.find('.criteria-list').append($block);
            });
        } catch (e) {}
    }
    updateEmptyState();

    // ── Tab switching ─────────────────────────────────────────────────────────

    $el.on('click', '.te-tab', function(e) {
        e.preventDefault();
        var tab = $(this).data('tab');
        $el.find('.te-tab').removeClass('active').attr('aria-selected', 'false');
        $(this).addClass('active').attr('aria-selected', 'true');
        $el.find('.te-tab-panel').removeClass('active');
        $el.find('.te-tab-panel[data-panel="' + tab + '"]').addClass('active');
    });

    // ── Collapse / expand criterion ───────────────────────────────────────────

    $el.on('click', '.criterion-toggle', function(e) {
        e.stopPropagation();
        $(this).closest('.criterion-block').toggleClass('collapsed');
    });

    $el.on('click', '.criterion-header', function(e) {
        if ($(e.target).is('input') || $(e.target).closest('button').length) return;
        $(this).closest('.criterion-block').toggleClass('collapsed');
    });

    // ── Add Criterion ─────────────────────────────────────────────────────────

    $el.on('click', '.add-criterion', function(e) {
        e.preventDefault();
        addCriterion();
        $el.find('.te-tab[data-tab="rubrics"]').trigger('click');
    });

    // ── Remove Criterion ──────────────────────────────────────────────────────

    $el.on('click', '.del-criterion', function(e) {
        e.stopPropagation();
        var $block = $(this).closest('.criterion-block');
        $block.slideUp(160, function() {
            $block.remove();
            renumberCriteria();
            updateEmptyState();
        });
    });

    // ── Add Option ────────────────────────────────────────────────────────────

    $el.on('click', '.add-option', function(e) {
        e.preventDefault();
        var $row = buildOptionRow();
        $(this).closest('.criterion-block').find('.option-rows').append($row);
        $row.find('.opt-name').focus();
    });

    // ── Remove Option ─────────────────────────────────────────────────────────

    $el.on('click', '.del-option', function() {
        var $row = $(this).closest('.option-row');
        $row.slideUp(140, function() { $row.remove(); });
    });

    // ── Numeric-only marks ────────────────────────────────────────────────────

    $el.on('keydown', '.opt-marks', function(e) {
        if (['e', 'E', '+', '-'].includes(e.key)) e.preventDefault();
    });

    $el.on('input', '.opt-marks', function() {
        var val = this.value;
        if (!/^\d*\.?\d*$/.test(val)) this.value = val.slice(0, -1);
    });

    // Clear errors as user starts typing
    $el.on('input', '.criterion-name', function() {
        var $block = $(this).closest('.criterion-block');
        $block.removeClass('te-has-error');
        $(this).removeClass('te-input-error');
        $(this).next('.te-field-error').remove();
    });

    $el.on('input', '.opt-name', function() {
        var $row = $(this).closest('.option-row');
        $row.removeClass('te-has-error');
        $(this).removeClass('te-input-error');
        $(this).next('.te-field-error').remove();
    });

    $el.on('input', '#tas_edit_display_name', function() {
        $(this).removeClass('te-input-error');
        $(this).next('.te-field-error').remove();
        $el.find('.te-validation-banner').remove();
    });

    // ── Save / Cancel button binding ──────────────────────────────────────────
    // Open edX Studio moves .xblock-actions to the modal footer before calling
    // the init function, so $el.find('.action-save') would find nothing.
    // Walk up to the nearest modal wrapper to find the relocated buttons.

    var $modalCtx = $el.closest('.wrapper-comp-editor, .modal-window, .xblock-editor');
    if (!$modalCtx.length) $modalCtx = $el.parent();

    $modalCtx.find('.action-cancel').off('click.tas').on('click.tas', function(e) {
        e.preventDefault();
        runtime.notify('cancel', {});
    });

    $modalCtx.find('.action-save').off('click.tas').on('click.tas', function(e) {
        e.preventDefault();

        if (!validate()) return;

        var rubrics = [];
        $el.find('.criterion-block').each(function() {
            var criterionName = $(this).find('.criterion-name').val().trim();
            if (!criterionName) return;

            var options = [];
            $(this).find('.option-row').each(function() {
                var name  = $(this).find('.opt-name').val().trim();
                var desc  = $(this).find('.opt-desc').val().trim();
                var marks = parseFloat($(this).find('.opt-marks').val()) || 0;
                if (name || desc) {
                    options.push({ name: name, marks: marks, description: desc });
                }
            });

            rubrics.push({ criterion: criterionName, options: options });
        });

        var data = {
            display_name:  $el.find('#tas_edit_display_name').val(),
            template_type: $el.find('#tas_edit_template_type').val(),
            template:      $el.find('#tas_edit_template').val(),
            instructions:  $el.find('#tas_edit_instructions').val(),
            rubrics:       rubrics,
        };

        runtime.notify('save', { state: 'start' });

        $.ajax({
            type:        'POST',
            url:         runtime.handlerUrl(element, 'save_studio'),
            data:        JSON.stringify(data),
            contentType: 'application/json',
        }).done(function(response) {
            if (response.result === 'success') {
                runtime.notify('save', { state: 'end' });
            } else {
                runtime.notify('error', { msg: response.message });
            }
        });
    });
}
