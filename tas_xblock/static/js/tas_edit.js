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
    function addRow(criteria='', description='', marks='') {
        var row = `
            <tr>
                <td><input type="text" class="crit" value="${criteria}"></td>
                <td><input type="text" class="desc" value="${description}"></td>
                <td>
                    <input type="text" class="marks" value="${marks}">
                </td>
                <td><button type="button" class="del">X</button></td>
            </tr>
        `;
        $(element).find('.rubric-rows').append(row);
    }

    // LOAD EXISTING
    var dataRubrics = $(element).find('#settings-tab').attr('data-rubrics');

    if (dataRubrics && dataRubrics !== "[]") {
        try {
            var rubrics = JSON.parse(dataRubrics);
            rubrics.forEach(function(r) {
                addRow(r.criteria, r.description, r.marks);
            });
        } catch (e) {}
    }

    $(element).on('keydown', '.marks', function(e) {
        if (['e', 'E', '+', '-'].includes(e.key)) {
            e.preventDefault();
        }
    });
    // ===== ONLY NUMBER INPUT =====
    $(element).on('input', '.marks', function () {
        let val = this.value;

        // allow only numbers + ONE dot
        if (!/^\d*\.?\d*$/.test(val)) {
            this.value = val.slice(0, -1);
        }
    });
    // ADD
    $(element).on('click', '.add-rubric', function(e) {
        e.preventDefault();
        addRow();
    });

    // DELETE
    $(element).on('click', '.del', function(e) {
        e.preventDefault();
        $(this).closest('tr').remove();
    });

    // ================= CANCEL =================
    $(element).find('.action-cancel').on('click', function() {
        runtime.notify('cancel', {});
    });

    // ================= SAVE =================
    $(element).find('.action-save').on('click', function() {

        // collect rubrics
        var rubrics = [];
        $(element).find('.rubric-rows tr').each(function() {
            let criteria = $(this).find('.crit').val();
            let description = $(this).find('.desc').val();
            let marks = parseFloat($(this).find('.marks').val()) || 0;

            if (criteria || description) {
                rubrics.push({
                    criteria: criteria,
                    description: description,
                    marks: marks
                });
            }
        });

        var data = {
            'display_name': $(element).find('#tas_edit_display_name').val(),
            'template_type': $(element).find('#tas_edit_template_type').val(),
            'template': $(element).find('#tas_edit_template').val(),
            'instructions': $(element).find('#tas_edit_instructions').val(),
            'rubrics': rubrics
        };
        
        runtime.notify('save', {state: 'start'});
        
        var handlerUrl = runtime.handlerUrl(element, 'save_studio');

        $.ajax({type: "POST", url: handlerUrl, data: JSON.stringify(data), contentType: "application/json", }).done(function(response) {
            if (response.result === 'success') {
                runtime.notify('save', {state: 'end'});
            } else {
                runtime.notify('error', {msg: response.message});
            }
        });
    });
}

