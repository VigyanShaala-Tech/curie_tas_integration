/* Javascript for TASXBlock. */
function TASXBlockInitEdit(runtime, element) {

    // ================= TABS =================
    $(element).on('click', '.tab-btn', function(e) {
        e.preventDefault();

        var tab = $(this).data('tab');

        $(element).find('.tab-btn').removeClass('active');
        $(this).addClass('active');

        $(element).find('.tab-content').removeClass('active');
        $(element).find('.' + tab + '-tab').addClass('active');
    });

    // ================= RUBRICS =================

    function addOption(tbody, name, marks, description) {
        name        = name        || '';
        marks       = marks       !== undefined ? marks : '';
        description = description || '';

        var row = $('<tr class="option-row">' +
            '<td><input type="text"   class="opt-name"  placeholder="Option name"  value="' + escAttr(name)        + '"></td>' +
            '<td><input type="text"   class="opt-marks" placeholder="0"             value="' + escAttr(String(marks)) + '"></td>' +
            '<td><input type="text"   class="opt-desc"  placeholder="Description"   value="' + escAttr(description) + '"></td>' +
            '<td><button type="button" class="del-option">&#10005;</button></td>' +
        '</tr>');

        tbody.append(row);
    }

    function addCriterion(criterion, options) {
        criterion = criterion || '';
        options   = options   || [];

        var block = $(
            '<div class="criterion-block">' +
                '<div class="criterion-header">' +
                    '<input type="text" class="criterion-name" placeholder="Criterion name" value="' + escAttr(criterion) + '">' +
                    '<button type="button" class="del-criterion">&#10005; Remove Criterion</button>' +
                '</div>' +
                '<table class="options-table">' +
                    '<thead><tr>' +
                        '<th>Option Name</th>' +
                        '<th>Marks</th>' +
                        '<th>Description</th>' +
                        '<th>Delete</th>' +
                    '</tr></thead>' +
                    '<tbody class="option-rows"></tbody>' +
                '</table>' +
                '<button type="button" class="add-option">+ Add Option</button>' +
            '</div>'
        );

        var tbody = block.find('.option-rows');
        options.forEach(function(opt) {
            addOption(tbody, opt.name, opt.marks, opt.description);
        });

        $(element).find('.criteria-list').append(block);
    }

    // Escape attribute values
    function escAttr(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    // ----- Load existing rubrics -----
    var dataRubrics = $(element).find('#settings-tab').attr('data-rubrics');
    if (dataRubrics && dataRubrics !== '[]') {
        try {
            var rubrics = JSON.parse(dataRubrics);
            rubrics.forEach(function(r) {
                addCriterion(r.criterion, r.options || []);
            });
        } catch (e) {}
    }

    // ----- Add Criterion -----
    $(element).on('click', '.add-criterion', function(e) {
        e.preventDefault();
        addCriterion();
    });

    // ----- Remove Criterion -----
    $(element).on('click', '.del-criterion', function(e) {
        e.preventDefault();
        $(this).closest('.criterion-block').remove();
    });

    // ----- Add Option -----
    $(element).on('click', '.add-option', function(e) {
        e.preventDefault();
        var tbody = $(this).closest('.criterion-block').find('.option-rows');
        addOption(tbody);
    });

    // ----- Remove Option -----
    $(element).on('click', '.del-option', function(e) {
        e.preventDefault();
        $(this).closest('tr').remove();
    });

    // ----- Block non-numeric keys in marks fields -----
    $(element).on('keydown', '.opt-marks', function(e) {
        if (['e', 'E', '+', '-'].includes(e.key)) {
            e.preventDefault();
        }
    });
    $(element).on('input', '.opt-marks', function() {
        var val = this.value;
        if (!/^\d*\.?\d*$/.test(val)) {
            this.value = val.slice(0, -1);
        }
    });

    // ================= CANCEL =================
    $(element).find('.action-cancel').on('click', function() {
        runtime.notify('cancel', {});
    });

    // ================= SAVE =================
    $(element).find('.action-save').on('click', function() {

        // Collect criteria and their options
        var rubrics = [];
        $(element).find('.criterion-block').each(function() {
            var criterionName = $(this).find('.criterion-name').val().trim();
            if (!criterionName) return;

            var options = [];
            $(this).find('.option-rows tr').each(function() {
                var name  = $(this).find('.opt-name').val().trim();
                var marks = parseFloat($(this).find('.opt-marks').val()) || 0;
                var desc  = $(this).find('.opt-desc').val().trim();
                if (name || desc) {
                    options.push({ name: name, marks: marks, description: desc });
                }
            });

            rubrics.push({ criterion: criterionName, options: options });
        });

        var data = {
            display_name:  $(element).find('#tas_edit_display_name').val(),
            template_type: $(element).find('#tas_edit_template_type').val(),
            template:      $(element).find('#tas_edit_template').val(),
            instructions:  $(element).find('#tas_edit_instructions').val(),
            rubrics:       rubrics,
        };

        runtime.notify('save', { state: 'start' });

        var handlerUrl = runtime.handlerUrl(element, 'save_studio');
        $.ajax({
            type:        'POST',
            url:         handlerUrl,
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
