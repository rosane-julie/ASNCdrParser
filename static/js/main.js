// Main JavaScript file for ASN.1 CDR Parser

$(document).ready(function() {
    // Initialize DataTables if present
    if ($('#cdrTable').length) {
        $('#cdrTable').DataTable({
            "pageLength": 25,
            "responsive": true,
            "order": [[ 0, "asc" ]],
            "columnDefs": [
                { "orderable": false, "targets": -1 } // Disable ordering on Actions column
            ],
            "language": {
                "search": "Search records:",
                "lengthMenu": "Show _MENU_ records per page",
                "info": "Showing _START_ to _END_ of _TOTAL_ records",
                "paginate": {
                    "first": "First",
                    "last": "Last",
                    "next": "Next",
                    "previous": "Previous"
                }
            }
        });
    }
    
    // Auto-hide flash messages after 5 seconds
    setTimeout(function() {
        $('.alert-dismissible').fadeOut();
    }, 5000);
    
    // File upload validation
    $('input[type="file"]').on('change', function() {
        var file = this.files[0];
        if (file) {
            var maxSize = 100 * 1024 * 1024; // 100MB
            if (file.size > maxSize) {
                alert('File size exceeds 100MB limit. Please select a smaller file.');
                $(this).val('');
                return false;
            }
            
            // Check file extension
            var allowedExtensions = ['dat', 'cdr', 'bin', 'asn1', 'ber', 'der'];
            var fileExtension = file.name.split('.').pop().toLowerCase();
            
            if (allowedExtensions.indexOf(fileExtension) === -1) {
                alert('Invalid file type. Allowed extensions: ' + allowedExtensions.join(', '));
                $(this).val('');
                return false;
            }
        }
    });
    
    // Confirm delete actions
    $('form[onsubmit*="confirm"]').on('submit', function(e) {
        if (!confirm('Are you sure you want to delete this file? This action cannot be undone.')) {
            e.preventDefault();
            return false;
        }
    });
    
    // Tooltip initialization
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Copy to clipboard functionality
    $('.copy-to-clipboard').on('click', function() {
        var text = $(this).data('text');
        navigator.clipboard.writeText(text).then(function() {
            // Show success message
            var btn = $(this);
            var originalText = btn.html();
            btn.html('<i class="fas fa-check"></i> Copied!');
            setTimeout(function() {
                btn.html(originalText);
            }, 2000);
        });
    });
});

// Utility functions
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    if (!seconds) return '-';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

// Export functions
function exportData(fileId, format) {
    window.location.href = `/export/${fileId}/${format}`;
}

// Search and filter helpers
function applyFilters() {
    const form = document.querySelector('form[method="GET"]');
    if (form) {
        form.submit();
    }
}

function clearFilters() {
    const searchInput = document.querySelector('input[name="search"]');
    const typeSelect = document.querySelector('select[name="record_type"]');
    
    if (searchInput) searchInput.value = '';
    if (typeSelect) typeSelect.value = '';
    
    applyFilters();
}
