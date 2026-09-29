 const $ = selector => document.querySelector(selector);
  const $$ = selector => document.querySelectorAll(selector);


  // 折叠功能
  const app = document.getElementById("app");

function initResizeButtons() {
    const bLS = document.getElementById("btnLS");
    const bUS = document.getElementById("btnUS");

    if (bLS) bLS.textContent = "«";
    if (bUS) bUS.textContent = "«";
}

function state() {
    return {
        hasLS: !app.classList.contains("collapse-ls"),
        hasUS: !app.classList.contains("collapse-us")
    };
}

function applyCollapse(ls, us) {
    app.classList.toggle("collapse-ls", !ls);
    app.classList.toggle("collapse-us", !us);
    app.classList.toggle("collapse-both", !ls && !us);

    const btnLS = document.getElementById("btnLS");
    const btnUS = document.getElementById("btnUS");

    if (btnLS) btnLS.textContent = ls ? "«" : "»";
    if (btnUS) btnUS.textContent = us ? "«" : "»";
}

  function createDocumentItem(doc) {
    const div = document.createElement('div');
    div.className = 'document-item';
    div.textContent = doc.title || doc.filename || doc.name || 'untitled';
    div.dataset.docId = doc.id;
    div.dataset.fileName = doc.filename || doc.name || 'untitled';
    div.draggable = true;

    div.onclick = (e) => {
    e.stopPropagation();

    document.querySelectorAll('.document-item.selected').forEach(item => {
        item.classList.remove('selected');
    });

    div.classList.add('selected');

    window.selectedDocId = doc.id;
    window.selectedDocName = doc.filename;

    console.log('Selected document:', window.selectedDocId);

    // =====================================================
    // STEP 9C — UPDATE SELECTED DOCUMENT INFORMATION
    // =====================================================

    const selectedDocumentTitle =
        document.getElementById('selected-document-title');

    const selectedDocumentFilename =
        document.getElementById('selected-document-filename');

    const selectedDocumentType =
        document.getElementById('selected-document-type');

    const selectedPaperStatus =
        document.getElementById('selectedPaperStatus');

    const documentTitle =
        doc.title ||
        doc.filename ||
        doc.name ||
        'Untitled Research Paper';

    const documentFilename =
        doc.filename ||
        doc.name ||
        'Document file';
    // =====================================================
// STEP 12B — ENHANCED DOCUMENT INFORMATION
// =====================================================

const selectedDocumentCategory =
    document.getElementById('selected-document-category');

const selectedDocumentDate =
    document.getElementById('selected-document-date');

const selectedDocumentWordCount =
    document.getElementById('selected-document-word-count');

const selectedDocumentStatus =
    document.getElementById('selected-document-status');

const documentCategory =
    doc.category ||
    doc.category_name ||
    'Research Paper';

const documentDate =
    doc.created_at ||
    doc.upload_date ||
    doc.uploaded_at ||
    '—';

const documentWordCount =
    doc.word_count ||
    doc.words ||
    '—';

// Update category
if (selectedDocumentCategory) {
    selectedDocumentCategory.textContent = documentCategory;
}

// Update upload date
if (selectedDocumentDate) {
    selectedDocumentDate.textContent = documentDate;
}

// Update word count
if (selectedDocumentWordCount) {
    selectedDocumentWordCount.textContent = documentWordCount;
}

// Update summary status
if (selectedDocumentStatus) {
    selectedDocumentStatus.textContent = 'Not Generated';
}

    // Detect file type
    let documentType = 'DOCUMENT';

    if (documentFilename.toLowerCase().endsWith('.pdf')) {
        documentType = 'PDF';
    }
    else if (documentFilename.toLowerCase().endsWith('.docx')) {
        documentType = 'DOCX';
    }
    else if (documentFilename.toLowerCase().endsWith('.doc')) {
        documentType = 'DOC';
    }
    else {
        const extension = documentFilename.split('.').pop();

        if (
            extension &&
            extension !== documentFilename &&
            extension.length <= 5
        ) {
            documentType = extension.toUpperCase();
        }
    }

    // Update selected document card
    if (selectedDocumentTitle) {
        selectedDocumentTitle.textContent = documentTitle;
    }

    if (selectedDocumentFilename) {
        selectedDocumentFilename.textContent = documentFilename;
    }

    if (selectedDocumentType) {
        selectedDocumentType.textContent = documentType;
    }

    // Update workspace overview status
    if (selectedPaperStatus) {
        selectedPaperStatus.textContent = 'Selected';
    }

    // Continue existing summary workflow
    loadSummaryForSelectedDoc(doc.id);
};


    const delBtn = document.createElement('button');
    delBtn.className = 'document-delete-btn';
    delBtn.textContent = '🗑';
    delBtn.onclick = async (e) => {
      e.stopPropagation();
      if (confirm(`Delete "${div.dataset.fileName}"?`)) {
        await fetch(`/delete-document/${doc.id}`, { method: 'GET' });
        await loadDocuments();
      }
    };

    div.addEventListener('dragstart', function(e) {
      this.classList.add('dragging');
      e.dataTransfer.setData('text/plain', JSON.stringify({ docId: this.dataset.docId, fileName: this.dataset.fileName }));
      e.dataTransfer.effectAllowed = 'move';
    });

    div.addEventListener('dragend', function() { 
      this.classList.remove('dragging'); 
    });

    div.appendChild(delBtn);
    return div;
  }

  async function loadDocuments() {
    try {
      const res = await fetch('/get-documents');
      if (!res.ok) throw new Error('Failed to fetch documents');
      const docs = await res.json();
      const container = $('#documents-container');
      container.innerHTML = '';
      if (!Array.isArray(docs) || docs.length === 0) {
        container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px;">No documents found</div>';
        return;
      }
      docs.forEach(doc => container.appendChild(createDocumentItem(doc)));
      const paperCount =
    document.getElementById('paperCount');

if (paperCount) {

    paperCount.textContent =
        String(docs.length);

}

updateWorkspaceOverview();
    } catch (err) {
      console.error('Error loading documents:', err);
      const container = $('#documents-container');
      container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px;">Unable to load documents</div>';
    }
  }

  // Category management - 保持所有数据库连接不变
  let categories = [];
  let documentCategories = {};
  let currentCategory = 'all';

  // =========================================================
// Dashboard overview counters
// =========================================================
function updateWorkspaceOverview() {

    const paperCount =
        document.getElementById('paperCount');

    const categoryCount =
        document.getElementById('categoryCount');

    const selectedPaperStatus =
        document.getElementById('selectedPaperStatus');


    // Update category count
    if (categoryCount) {

        categoryCount.textContent =
            String(categories.length);

    }


    // Update selected paper
    if (selectedPaperStatus) {

        selectedPaperStatus.textContent =
            window.selectedDocName || 'None';

    }
}

  async function loadCategories() {
    try {
      const res = await fetch('/get_categories');
      if (!res.ok) throw new Error('Failed to load categories');
      categories = await res.json();
    } catch (err) {
      console.error('Error loading categories:', err);
      categories = [];
    }
    renderCategories();
    updateWorkspaceOverview();
  }

  function saveCategories() {
    localStorage.setItem('userCategories', JSON.stringify(categories));
    localStorage.setItem('documentCategories', JSON.stringify(documentCategories));
  }

  async function addCategory(name) {
    if (!name || !name.trim()) { alert('Category name cannot be empty.'); return; }
    try {
      const res = await fetch('/add_category', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ name: name.trim() }) 
      });
      const result = await res.json();
      if (result.success) { 
        categories.unshift({ id: result.id, name: result.name }); 
        renderCategories(); 
      } else {
        alert('Failed to add category: ' + (result.error || 'Unknown error'));
      }
    } catch (err) { 
      console.error('Error adding category:', err); 
      alert('Error adding category. See console.'); 
    }
  }

  async function deleteCategory(categoryId) {
    if (!confirm('Are you sure you want to delete this category? Documents will be moved back to All Documents.')) return;
    try {
      const res = await fetch(`/delete_category/${categoryId}`, { method: 'DELETE' });
      const result = await res.json();
      if (result.success) {
        categories = categories.filter(cat => String(cat.id) !== String(categoryId));
        if (currentCategory === String(categoryId)) setCurrentCategory('all');
        renderCategories();
        loadDocuments();
      } else {
        alert('Failed to delete category: ' + (result.error || 'Unknown error'));
      }
    } catch (err) { 
      console.error('Error deleting category:', err); 
      alert('Error deleting category. See console.'); 
    }
  }

  function setupDropZone(categoryElement) {
    categoryElement.addEventListener('dragover', function(e) { 
      e.preventDefault(); 
      e.dataTransfer.dropEffect = 'move'; 
      this.classList.add('drag-over'); 
    });
    
    categoryElement.addEventListener('dragleave', function(e) { 
      if (!this.contains(e.relatedTarget)) this.classList.remove('drag-over'); 
    });
    
    categoryElement.addEventListener('drop', async function(e) {
      e.preventDefault(); 
      this.classList.remove('drag-over');
      try {
        const dragData = JSON.parse(e.dataTransfer.getData('text/plain'));
        const targetCategory = this.dataset.category;
        const response = await fetch('/update-document-category', { 
          method: 'POST', 
          headers: { 'Content-Type': 'application/json' }, 
          body: JSON.stringify({ 
            documentId: dragData.docId, 
            category: targetCategory === 'all' ? null : targetCategory 
          }) 
        });
        if (response.ok) {
          if (targetCategory === 'all') {
            delete documentCategories[dragData.docId];
          } else {
            documentCategories[dragData.docId] = targetCategory;
          }
          saveCategories();
          loadDocuments();
          console.log(`Moved "${dragData.fileName}" to ${targetCategory === 'all' ? 'All Documents' : this.querySelector('.category-title').textContent}`);
        } else {
          alert('Failed to update document category');
        }
      } catch (err) { 
        console.error('Error handling drop:', err); 
      }
    });
  }

  function renderCategories() {
  const container = document.querySelector('.categories-container');

  // 🔹 Keep All Documents and remove others
  const existing = container.querySelectorAll('.category:not([data-category="all"])');
  existing.forEach(el => el.remove());

  // 🔹 Rebuild subfolders
  categories.forEach(category => {
    const categoryEl = document.createElement('div');
    categoryEl.className = 'category';
    categoryEl.dataset.category = String(category.id);

    const titleEl = document.createElement('div');
    titleEl.className = 'category-title';
    titleEl.textContent = category.name;

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-category';
    deleteBtn.textContent = '🗑';
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      deleteCategory(category.id);
    };

    categoryEl.appendChild(titleEl);
    categoryEl.appendChild(deleteBtn);
    categoryEl.onclick = () => setCurrentCategory(String(category.id));
    setupDropZone(categoryEl);
    container.appendChild(categoryEl);
  });

  // ✅ Always reattach click event to "All Documents"
  const allCategory = container.querySelector('.category[data-category="all"]');
  if (allCategory) {
    allCategory.onclick = () => setCurrentCategory('all');
  }

  // ✅ Maintain active highlight
  const activeEl = container.querySelector(`.category[data-category="${currentCategory}"]`);
  container.querySelectorAll('.category').forEach(c => c.classList.remove('active-category'));
  if (activeEl) activeEl.classList.add('active-category');
}

  

  function setCurrentCategory(categoryId) {
  currentCategory = categoryId;

  // Highlight active folder
  document.querySelectorAll('.category').forEach(c => c.classList.remove('active-category'));
  const el = document.querySelector(`.category[data-category="${categoryId}"]`);
  if (el) el.classList.add('active-category');

  // Update display text
  const categoryName = categoryId === 'all'
    ? 'All Documents'
    : (categories.find(cat => String(cat.id) === String(categoryId))?.name || categoryId);
  $('#current-category').textContent = `Showing: ${categoryName}`;

  // ✅ Update hidden folder_id input before upload
  const folderInput = document.getElementById('folder_id');
  if (folderInput) {
    folderInput.value = (categoryId === 'all') ? '' : categoryId;
  }

  const uploadBtn = document.getElementById('uploadBtn');
  if (uploadBtn) {
    if (categoryId === 'all') {
      uploadBtn.disabled = false;
      uploadBtn.classList.remove('disabled-upload');
    } else {
      uploadBtn.disabled = true;
      uploadBtn.classList.add('disabled-upload');
    }
  }

  // Refresh file list for selected folder
  filterDocuments();
}



async function filterDocuments() {
  try {
    const res = await fetch(`/get-documents?category=${currentCategory}`);
    if (!res.ok) throw new Error('Failed to fetch documents');

    const docs = await res.json();
    

    const container =
      document.getElementById('documents-container');

    container.innerHTML = '';

    if (!Array.isArray(docs) || docs.length === 0) {
      container.innerHTML =
        '<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px;">No documents in this category</div>';

      const paperCount =
        document.getElementById('paperCount');

      if (paperCount) {
        paperCount.textContent = 0;
      }

      return;
    }

    // =====================================================
    // STEP 10A — PART 2
    // SORT RESEARCH PAPERS
    // =====================================================

    const documentSort = document.getElementById('documentSort');

const sortLabel = documentSort
    ? documentSort.options[documentSort.selectedIndex].textContent.trim().toLowerCase()
    : 'newest first';

docs.sort((a, b) => {

    const nameA = (a.title || a.filename || a.name || '').trim().toLowerCase();
    const nameB = (b.title || b.filename || b.name || '').trim().toLowerCase();

    // A → Z
    if (sortLabel.includes('a → z')) {
        return nameA.localeCompare(nameB);
    }

    // Z → A
    if (sortLabel.includes('z → a')) {
        return nameB.localeCompare(nameA);
    }

    // Document ID is currently our upload sequence.
    const idA = Number(a.id) || 0;
    const idB = Number(b.id) || 0;

    // Oldest First
    if (sortLabel.includes('oldest')) {
        return idA - idB;
    }

    // Newest First
    return idB - idA;
});

    // =====================================================
    // CREATE DOCUMENT CARDS
    // =====================================================

    docs.forEach(doc => {
      container.appendChild(
        createDocumentItem(doc)
      );
    });

    // =====================================================
    // UPDATE PAPER COUNT
    // =====================================================

    const paperCount =
      document.getElementById('paperCount');

    if (paperCount) {
      paperCount.textContent = docs.length;
    }

  } catch (err) {

    console.error(
      'Error filtering documents:',
      err
    );
  }
}


 // ✅ Template Modal - Final Fixed Version
const modal = document.getElementById('templateModal');
  const categoryList = document.getElementById('categoryList');
  const templateCards = document.getElementById('templateCards');
  const categoryTitle = document.getElementById('categoryTitle');
  const generateNowBtn = document.getElementById('generateNowBtn');
  const generateBtn = document.getElementById('generateBtn'); // <-- important

  let allTemplates = [];
  let selectedCategory = null;
  let selectedTemplateId = null;

  // Open modal when "Generate" is clicked
  // Open modal when "Generate" is clicked
if (generateBtn) {
  generateBtn.addEventListener('click', async () => {
    // Check membership level first
    

    if (!window.selectedDocId) {
      alert('⚠️ Please select a document first before generating.');
      return;
    }

    // Open modal for template selection
    modal.classList.remove('hidden');
    await loadTemplates();
  });
}
  // Load templates
  async function loadTemplates() {
    try {
      const res = await fetch('/get_templates');

if (!res.ok) {
  throw new Error(`Failed to load templates: ${res.status}`);
}

const data = await res.json();

if (!data.success) {
    throw new Error(
        data.error || 'Unable to load templates'
    );
}

allTemplates = data.templates || [];

console.log(
    'Membership:',
    data.membership
);

console.log(
    'Available templates:',
    allTemplates.length
);

      

      const categories = [...new Set(allTemplates.map(t => t.category || 'Uncategorized'))];
      categoryList.innerHTML = '';
      categories.forEach((cat, index) => {
    const li = document.createElement('li');

    li.textContent = cat;

    li.onclick = () => {
        showTemplatesByCategory(cat, li);
    };

  categoryList.appendChild(li);

  // Automatically select the first category
  if (index === 0) {
    showTemplatesByCategory(cat, li);
  }
});
    } catch (err) {
  console.error('Failed to load templates:', err);

  categoryList.innerHTML = '';
  templateCards.innerHTML = `
    <div class="template-error-message">
      Unable to load templates.
      Please refresh the page and try again.
    </div>
  `;
  categoryTitle.textContent = 'Templates unavailable';
}
  }

  function showTemplatesByCategory(category, el) {
    selectedCategory = category;
    document.querySelectorAll('#categoryList li').forEach(li => li.classList.remove('active'));
    el.classList.add('active');
    categoryTitle.textContent = category;

    const filtered = allTemplates.filter(t => (t.category || 'Uncategorized') === category);
    templateCards.innerHTML = filtered.map(t => `
    <div class="template-card" data-id="${t.id}">

        <div class="template-card-top">
            <div class="template-card-icon" aria-hidden="true">
    AI
</div>

            <div class="template-card-heading">
                <span class="template-card-category">
                    ${t.category || 'General'}
                </span>

                <h4>${t.name}</h4>
            </div>
        </div>

        <p class="template-card-description">
            Structured AI analysis designed for
            ${t.category || 'research'} documents.
        </p>

        <div class="template-card-footer">
            <span class="template-card-action">
                Select template
            </span>

            <span class="template-card-arrow">→</span>
        </div>

    </div>
`).join('');

    document.querySelectorAll('.template-card').forEach(card => {
      card.addEventListener('click', () => selectTemplate(card));
    });
  }

  function selectTemplate(card) {
    document.querySelectorAll('.template-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    selectedTemplateId = card.getAttribute('data-id');
  }

  function closeTemplateModal() {
    modal.classList.add('hidden');
    selectedTemplateId = null;
    document.querySelectorAll('.template-card').forEach(c => c.classList.remove('selected'));
  }

generateNowBtn.addEventListener('click', async () => {
  if (!selectedTemplateId) {
    alert('Please select a template first.');
    return;
  }

  // =====================================================
  // STEP 9D — PART 3
  // AI SUMMARY LOADING STATE
  // =====================================================

  generateNowBtn.disabled = true;

  generateNowBtn.dataset.originalText =
    generateNowBtn.textContent;

  generateNowBtn.innerHTML = `
    <span class="summary-btn-spinner"></span>
    Generating Summary...
  `;

  generateNowBtn.classList.add('generating');

  const loader = document.getElementById("fullscreenLoader");
  const outputDiv = document.getElementById("generatedText");

  loader.style.display = "flex";
  outputDiv.textContent = "";

  const template = allTemplates.find(t => t.id == selectedTemplateId);

  try {
    const summaryRes = await fetch("/generateSummary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_name: window.selectedDocName,
        document_id: window.selectedDocId,
        template_prompt: template.prompt,
        summaryTemplate:selectedTemplateId
      })
    });

    const data = await summaryRes.json();
if (data.summary) {

    // sanitize then render HTML
    const clean = DOMPurify.sanitize(data.summary);

    outputDiv.classList.add('professional-summary-output');

    outputDiv.innerHTML = clean;

    // =====================================================
    // STEP 9E — PART 3
    // ADD SUMMARY TO HISTORY
    // =====================================================

    addSummaryToHistory({
        documentName: window.selectedDocName || "Research Paper",
        templateName: template.name || "AI Summary",
        time: "Just now"
    });

} else {
  outputDiv.textContent = "❌ Error: " + (data.error || "Unknown error");
}


  } catch (err) {
    outputDiv.textContent = "Server error. Please check the console or try again.";
    console.error(err);

  } finally {
    loader.style.display = "none"; // ✅ HIDE POPUP OVERLAY

    // Restore Generate Summary button
    generateNowBtn.disabled = false;

    generateNowBtn.textContent =
        generateNowBtn.dataset.originalText ||
        "Generate Summary";

    generateNowBtn.classList.remove("generating");
}

  closeTemplateModal();
});


  // Close modal when clicking outside
  window.addEventListener('click', (e) => {
    if (e.target === modal) closeTemplateModal();
  });

  const addCategoryBtn = document.getElementById('addCategoryBtn');

if (addCategoryBtn) {
  addCategoryBtn.addEventListener('click', async () => {
    const name = prompt('Enter a name for the new category (subfolder):');

    if (name && name.trim()) {
      await addCategory(name.trim());
    }
  });
}
  
document.addEventListener('DOMContentLoaded', () => {
  try {
    // init UI controls (resizer buttons)
    initResizeButtons();

    // load categories and documents into UI
    loadCategories();
    loadDocuments();

    // setup collapse button labels (safe guard)
    const s = state();
    const btnLS = document.getElementById('btnLS');
    const btnUS = document.getElementById('btnUS');
    if (btnLS) btnLS.textContent = s.hasLS ? '«' : '»';
    if (btnUS) btnUS.textContent = s.hasUS ? '«' : '»';

    // wire buttons if not already wired earlier
    if (btnLS) btnLS.onclick = () => { const st = state(); applyCollapse(!st.hasLS, st.hasUS); };
    if (btnUS) btnUS.onclick = () => { const st = state(); applyCollapse(st.hasLS, !st.hasUS); };
  } catch (err) {
    console.error('Init error:', err);
  }
});



  const uploadBtn = document.getElementById('uploadBtn');
const uploadModal = document.getElementById('uploadModal');
const cancelUpload = document.getElementById('cancelUpload');
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileNameDisplay = document.getElementById('fileNameDisplay');
  

// 🟢 Open popup
uploadBtn.addEventListener('click', () => {
  uploadModal.style.display = 'flex';  // show overlay
});

// 🔴 Close popup
cancelUpload.addEventListener('click', () => {
  uploadModal.style.display = 'none';
  document.getElementById('modalUploadForm').reset();
});

// 🧲 Drag & drop zone
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('active');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('active'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  fileInput.files = e.dataTransfer.files;
  dropZone.classList.remove('active');
  // ✅ Show dropped file name
  if (fileInput.files.length > 0) {
    fileNameDisplay.textContent = `Selected: ${fileInput.files[0].name}`;
  }
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length > 0) {
    fileNameDisplay.textContent = `Selected: ${fileInput.files[0].name}`;
  } else {
    fileNameDisplay.textContent = '';
  }
});
document.getElementById("downloadBtn").addEventListener("click", () => {
    const filename = "summary_"+window.selectedDocId+".pdf";
    const summaryText = document.getElementById("generatedText").innerText.trim();

    if (filename.includes("undefined")) {
        alert("⚠️ Please select a document first.");
        return;
    }
    if (!summaryText) {
        alert("⚠️ No summary available. Please generate summary first.");
        return;
    }
    window.location.href = `/download_summary/${window.selectedDocId}`;
});

async function loadSummaryForSelectedDoc(docId) {
  const outputDiv = document.getElementById("generatedText");
  outputDiv.textContent = "⏳ Checking summary...";

  try {
    const res = await fetch(`/getSummary/${docId}`);
    const data = await res.json();

    if (data.summary) {
  const clean = DOMPurify.sanitize(data.summary);

  outputDiv.classList.add('professional-summary-output');

  outputDiv.innerHTML = clean;
} else {
  outputDiv.textContent = "📄 No summary generated yet for this document.";
}


  } catch (err) {
    outputDiv.textContent = "⚠️ Error fetching summary.";
    console.error(err);
  }
}


// Share to Forum functionality
document.getElementById('foreignerBtn').addEventListener('click', async () => {
  if (!window.selectedDocId) {
    alert('⚠️ Please select a document first.');
    return;
  }

  const outputDiv = document.getElementById('generatedText');
  const summaryText = outputDiv.textContent.trim();
  
  if (!summaryText || summaryText.includes('No summary generated yet')) {
    alert('⚠️ Please generate a summary first before sharing.');
    return;
  }

  const confirmed = confirm('📤 Share this summary to Community Forum?\n\nThis will make your summary visible to all users (anonymously).');
  
  if (!confirmed) return;

  try {
    const response = await fetch('/forum/share', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_id: window.selectedDocId })
    });

    const data = await response.json();

    if (data.success) {
      alert('✅ Summary shared successfully!\n\nVisit Community Forum to see your post.');
    } else {
      alert('❌ Failed to share: ' + (data.error || 'Unknown error'));
    }
  } catch (error) {
    console.error('Share error:', error);
    alert('❌ Error sharing summary. Please try again.');
  }
});

// =========================================================
// STEP 6A — UPLOAD BUTTON LOADING STATE
// =========================================================

const modalUploadForm = document.getElementById('modalUploadForm');
const addUpload = document.getElementById('addUpload');

if (modalUploadForm && addUpload) {

    modalUploadForm.addEventListener('submit', () => {

        // Prevent accidental double-click submission
        addUpload.disabled = true;

        // Show upload progress state
        addUpload.textContent = 'Uploading...';

        addUpload.classList.add('uploading');

    });

}


// =========================================================
// STEP 7C — RESEARCH PAPER SEARCH
// =========================================================

const documentSearch = document.getElementById('documentSearch');
const clearDocumentSearch = document.getElementById('clearDocumentSearch');

if (documentSearch) {

    documentSearch.addEventListener('input', () => {

        const searchText = documentSearch.value.trim().toLowerCase();
        const documentItems = document.querySelectorAll(
            '#documents-container .document-item'
        );

        let visibleCount = 0;

        documentItems.forEach(item => {

            const documentName = item.textContent
                .toLowerCase()
                .trim();

            if (documentName.includes(searchText)) {
                item.style.display = '';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }

        });

        // Show / hide clear button
        if (clearDocumentSearch) {
            clearDocumentSearch.style.display =
                searchText ? 'flex' : 'none';
        }

        // No matching papers message
        let noResults = document.getElementById(
            'documentSearchNoResults'
        );

        if (searchText && visibleCount === 0) {

            if (!noResults) {
                noResults = document.createElement('div');
                noResults.id = 'documentSearchNoResults';
                noResults.className = 'document-search-no-results';
                noResults.textContent = 'No matching research papers found.';
                document.getElementById(
                    'documents-container'
                ).appendChild(noResults);
            }

            noResults.style.display = 'block';

        } else if (noResults) {

            noResults.style.display = 'none';
        }
    });
}


// Clear search
if (clearDocumentSearch) {

    clearDocumentSearch.addEventListener('click', () => {

        if (documentSearch) {
            documentSearch.value = '';
            documentSearch.dispatchEvent(new Event('input'));
            documentSearch.focus();
        }

    });
}

// =========================================================
// STEP 9E — PART 3
// SUMMARY HISTORY FUNCTION
// =========================================================

function addSummaryToHistory(summaryData) {

    const historyList =
        document.getElementById("summaryHistoryList");

    const emptyState =
        document.getElementById("summaryHistoryEmpty");

    if (!historyList) {
        return;
    }

    // Hide empty state
    if (emptyState) {
        emptyState.style.display = "none";
    }

    const historyItem =
        document.createElement("div");

    historyItem.className =
        "summary-history-item";

    historyItem.innerHTML = `
        <div class="summary-history-item-main">

            <div class="summary-history-item-icon">
                ✦
            </div>

            <div class="summary-history-item-details">

                <strong>
                    ${escapeSummaryHistoryText(
                        summaryData.documentName
                    )}
                </strong>

                <span>
                    ${escapeSummaryHistoryText(
                        summaryData.time
                    )}
                </span>

            </div>

        </div>

        <div class="summary-history-item-meta">

            <span class="summary-history-template">
                ${escapeSummaryHistoryText(
                    summaryData.templateName
                )}
            </span>

            <span class="summary-history-time">
                ✓ Generated
            </span>

        </div>
    `;

    // Add newest summary at the top
    historyList.prepend(historyItem);
}


// Safely display text inside the history UI
function escapeSummaryHistoryText(value) {

    const div = document.createElement("div");

    div.textContent =
        value == null ? "" : String(value);

    return div.innerHTML;
}
// =========================================================
// STEP 9E — PART 4B
// LOAD SUMMARY HISTORY FROM DATABASE
// =========================================================

async function loadSummaryHistory() {

    const historyList =
        document.getElementById("summaryHistoryList");

    const emptyState =
        document.getElementById("summaryHistoryEmpty");

    if (!historyList) {
        return;
    }

    try {

        const response =
            await fetch("/getSummaryHistory");

        const data =
            await response.json();

        if (!response.ok || !data.success) {

            console.error(
                "Summary history error:",
                data.error || "Unable to load history."
            );

            return;
        }

        // Remove existing history items
        historyList
            .querySelectorAll(".summary-history-item")
            .forEach(item => item.remove());

        // No history
        if (!data.history || data.history.length === 0) {

            if (emptyState) {
                emptyState.style.display = "flex";
            }

            return;
        }

        // Hide empty state
        if (emptyState) {
            emptyState.style.display = "none";
        }

        // Add database history
        data.history.forEach(item => {

            const historyItem =
                document.createElement("div");

            historyItem.className =
                "summary-history-item";

            const documentName =
                item.document_title ||
                item.filename ||
                "Research Paper";

            const templateName =
                item.summarytemplateid
                    ? `Template ${item.summarytemplateid}`
                    : "AI Summary";

            const generatedTime =
                formatSummaryHistoryTime(
                    item.createdat
                );

            historyItem.innerHTML = `
                <div class="summary-history-item-main">

                    <div class="summary-history-item-icon">
                        ✦
                    </div>

                    <div class="summary-history-item-details">

                        <strong>
                            ${escapeSummaryHistoryText(
                                documentName
                            )}
                        </strong>

                        <span>
                            ${escapeSummaryHistoryText(
                                generatedTime
                            )}
                        </span>

                    </div>

                </div>

                <div class="summary-history-item-meta">

                    <span class="summary-history-template">
                        ${escapeSummaryHistoryText(
                            templateName
                        )}
                    </span>

                    <span class="summary-history-time">
                        ✓ Generated
                    </span>

                </div>
            `;

            historyList.appendChild(historyItem);
        });

    } catch (error) {

        console.error(
            "❌ Failed to load summary history:",
            error
        );
    }
}


// =========================================================
// FORMAT HISTORY DATE/TIME
// =========================================================

function formatSummaryHistoryTime(dateValue) {

    if (!dateValue) {
        return "Date unavailable";
    }

    const date =
        new Date(dateValue);

    if (Number.isNaN(date.getTime())) {
        return "Date unavailable";
    }

    return date.toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
}


// =========================================================
// LOAD HISTORY WHEN DASHBOARD OPENS
// =========================================================

document.addEventListener("DOMContentLoaded", () => {

    loadSummaryHistory();

});
// =========================================================
// STEP 9E — PART 5B
// CLEAR SUMMARY HISTORY
// =========================================================

const clearSummaryHistoryBtn =
    document.getElementById("clearSummaryHistoryBtn");

if (clearSummaryHistoryBtn) {

    clearSummaryHistoryBtn.addEventListener(
        "click",
        async () => {

            const confirmed = confirm(
                "⚠️ Clear all summary history?\n\n" +
                "Your research papers will NOT be deleted.\n\n" +
                "Only saved AI summaries will be removed."
            );

            if (!confirmed) {
                return;
            }

            clearSummaryHistoryBtn.disabled = true;
            clearSummaryHistoryBtn.textContent =
                "Clearing...";

            try {

                const response = await fetch(
                    "/clearSummaryHistory",
                    {
                        method: "DELETE"
                    }
                );

                const data =
                    await response.json();

                if (!response.ok || !data.success) {

                    alert(
                        "❌ " +
                        (
                            data.error ||
                            "Unable to clear summary history."
                        )
                    );

                    return;
                }

                // Remove history items from the screen
                const historyList =
                    document.getElementById(
                        "summaryHistoryList"
                    );

                if (historyList) {

                    historyList
                        .querySelectorAll(
                            ".summary-history-item"
                        )
                        .forEach(item => item.remove());
                }

                // Show empty state
                const emptyState =
                    document.getElementById(
                        "summaryHistoryEmpty"
                    );

                if (emptyState) {
                    emptyState.style.display = "flex";
                }

                alert(
                    "✅ Summary history cleared successfully."
                );

            } catch (error) {

                console.error(
                    "❌ Clear history error:",
                    error
                );

                alert(
                    "❌ Unable to clear summary history. " +
                    "Please try again."
                );

            } finally {

                clearSummaryHistoryBtn.disabled = false;
                clearSummaryHistoryBtn.textContent =
                    "Clear";
            }
        }
    );
}


// =====================================================
// STEP 10A — PART 3
// SORT CHANGE EVENT
// =====================================================

const documentSort =
  document.getElementById('documentSort');

if (documentSort) {

  documentSort.addEventListener(
    'change',
    () => {

      filterDocuments();

    }
  );
}

// =========================================
// SUMMARY COPY & PRINT ACTIONS
// =========================================

document.addEventListener("DOMContentLoaded", () => {

    const copySummaryBtn = document.getElementById("copySummaryBtn");
    const printSummaryBtn = document.getElementById("printSummaryBtn");
    const generatedText = document.getElementById("generatedText");

    // Copy AI summary
    if (copySummaryBtn) {
        copySummaryBtn.addEventListener("click", async () => {

            if (!generatedText) return;

            const summaryText = generatedText.innerText.trim();

            if (!summaryText || summaryText.includes("Your research summary will appear here")) {
                alert("There is no summary to copy.");
                return;
            }

            try {
                await navigator.clipboard.writeText(summaryText);

                const originalText = copySummaryBtn.innerHTML;
                copySummaryBtn.innerHTML = "✓ <span>Copied</span>";

                setTimeout(() => {
                    copySummaryBtn.innerHTML = originalText;
                }, 1800);

            } catch (error) {
                console.error("Copy failed:", error);
                alert("Unable to copy the summary.");
            }
        });
    }

    // Print AI summary
    if (printSummaryBtn) {
        printSummaryBtn.addEventListener("click", () => {

            if (!generatedText) return;

            const summaryHTML = generatedText.innerHTML;

            if (!summaryHTML.trim() ||
                summaryHTML.includes("Your research summary will appear here")) {
                alert("There is no summary to print.");
                return;
            }

            const printWindow = window.open("", "_blank", "width=900,height=700");

            if (!printWindow) {
                alert("Please allow pop-ups to print the summary.");
                return;
            }

            printWindow.document.write(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>IPaper — Research Summary</title>

                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            max-width: 900px;
                            margin: 40px auto;
                            padding: 0 30px;
                            color: #1f2937;
                            line-height: 1.7;
                        }

                        h1, h2, h3, h4 {
                            color: #111827;
                            line-height: 1.4;
                        }

                        h2 {
                            border-left: 4px solid #4f46e5;
                            padding-left: 12px;
                        }

                        p {
                            margin: 12px 0;
                        }

                        ul, ol {
                            padding-left: 28px;
                        }

                        li {
                            margin-bottom: 7px;
                        }

                        table {
                            width: 100%;
                            border-collapse: collapse;
                            margin: 20px 0;
                        }

                        th,
                        td {
                            border: 1px solid #d1d5db;
                            padding: 9px 11px;
                            text-align: left;
                            vertical-align: top;
                        }

                        th {
                            background: #f3f4f6;
                        }

                        blockquote {
                            border-left: 4px solid #9ca3af;
                            padding: 10px 15px;
                            background: #f9fafb;
                        }

                        @media print {
                            body {
                                margin: 20px;
                                padding: 0;
                            }
                        }
                    </style>
                </head>

                <body>
                    ${summaryHTML}
                </body>
                </html>
            `);

            printWindow.document.close();

            printWindow.focus();

            setTimeout(() => {
                printWindow.print();
            }, 500);
        });
    }

});

// =========================================
// CLEAR CURRENT SUMMARY
// =========================================

document.addEventListener("DOMContentLoaded", () => {

    const clearSummaryBtn = document.getElementById(
        "clearCurrentSummaryBtn"
    );

    const generatedText = document.getElementById(
        "generatedText"
    );

    if (clearSummaryBtn && generatedText) {

        clearSummaryBtn.addEventListener("click", () => {

            const confirmed = confirm(
                "Clear the current summary from the screen?"
            );

            if (!confirmed) return;

            generatedText.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">✦</div>
                    <h3>Your research summary will appear here</h3>
                    <p>
                        Select Generate to create an AI-powered summary.
                    </p>
                    <div>
                        <span>01 Select document</span>
                        <span>02 Generate</span>
                        <span>03 Review output</span>
                    </div>
                </div>
            `;

            generatedText.classList.remove(
                "professional-summary-output"
            );

        });

    }

});