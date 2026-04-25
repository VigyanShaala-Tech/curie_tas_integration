/* Javascript for TASXBlock Studio Edit */
function TASXBlockInitEdit(runtime, element) {

    var $el = $(element);

    // ── Helpers ───────────────────────────────────────────────────────────────

    function escAttr(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    var WARN_SVG =
        '<svg viewBox="0 0 20 20" fill="currentColor">' +
        '<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>' +
        '</svg>';

    // ── Template Type → Template filtering ───────────────────────────────────
    // Each <option> in the template dropdown carries data-type="<template_type_id>".
    // When the type changes we hide non-matching options and reset the selection
    // if the previously chosen template no longer belongs to the new type.

    var $typeSelect     = $el.find('#tas_edit_template_type');
    var $templateSelect = $el.find('#tas_edit_template');

    function filterTemplates() {
        var selectedType = $typeSelect.val();
        var $options     = $templateSelect.find('option[data-type]');

        if (!selectedType) {
            // No type selected — show all templates
            $options.show();
            return;
        }

        $options.each(function() {
            var matches = $(this).data('type') == selectedType;
            $(this).toggle(matches);
        });

        // If the currently selected template is now hidden, reset it
        var $chosen = $templateSelect.find('option:selected');
        if ($chosen.val() && $chosen.data('type') != selectedType) {
            $templateSelect.val('');
        }
    }

    $typeSelect.on('change', filterTemplates);
    // Run on load so the template list is already filtered when editing an
    // existing block that has a type pre-selected.
    filterTemplates();

    // ── Validation ────────────────────────────────────────────────────────────

    function clearErrors() {
        $el.find('.te-validation-banner').remove();
        $el.find('.te-field-error').remove();
        $el.find('.te-input-error').removeClass('te-input-error');
    }

    function showBanner(msg) {
        var $banner = $(
            '<div class="te-validation-banner">' + WARN_SVG + escAttr(msg) + '</div>'
        );
        $el.find('.te-tab-panel').prepend($banner);
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

        if (!$el.find('#tas_edit_display_name').val().trim()) {
            addInputError($el.find('#tas_edit_display_name'), 'Display name is required.');
            valid = false;
        }

        if (!valid) {
            showBanner('Please fix the errors below before saving.');
        }

        return valid;
    }

    // Clear errors as user types
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

        var data = {
            display_name:  $el.find('#tas_edit_display_name').val(),
            template_type: $el.find('#tas_edit_template_type').val(),
            template:      $el.find('#tas_edit_template').val(),
            instructions:  $el.find('#tas_edit_instructions').val(),
            rubric_id:     $el.find('#tas_edit_rubric_id').val(),
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
