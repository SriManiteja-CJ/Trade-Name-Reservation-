import React, { useState } from 'react';
import { API_BASE } from '../config';

export default function RegistrySearchTab({ lang, channel }) {
  const isAr = lang === 'ar';

  // Keyword Search State
  const [keyword, setKeyword] = useState('');
  const [limit, setLimit] = useState(10);
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  // Exact Duplicate Check State
  const [dupAr, setDupAr] = useState('');
  const [dupEn, setDupEn] = useState('');
  const [dupExcludeId, setDupExcludeId] = useState('');
  const [dupResult, setDupResult] = useState(null);
  const [dupLoading, setDupLoading] = useState(false);

  // Perform Keyword Search (F19, F22)
  const handleKeywordSearch = async (e) => {
    e?.preventDefault();
    if (!keyword.trim()) return;

    setSearchLoading(true);
    setSearchResults(null);
    try {
      const resp = await fetch(
        `${API_BASE}/TradeName/Search?Keyword=${encodeURIComponent(keyword.trim())}&Limit=${limit}`,
        {
          headers: {
            'X-Channel': channel,
            'Accept-Language': isAr ? 'ar' : 'en',
          },
        }
      );
      if (!resp.ok) {
        throw new Error(`Search failed: ${resp.status}`);
      }
      const data = await resp.json();
      setSearchResults(data);
    } catch (err) {
      alert(`Search error: ${err.message}`);
    } finally {
      setSearchLoading(false);
    }
  };

  // Perform Exact Duplicate Check (F2)
  const handleDuplicateCheck = async (e) => {
    e?.preventDefault();
    if (!dupAr.trim() && !dupEn.trim()) {
      alert(isAr ? 'يرجى إدخال اسم بالعربية أو الإنجليزية' : 'Please provide at least one Arabic or English name');
      return;
    }

    setDupLoading(true);
    setDupResult(null);
    try {
      const params = new URLSearchParams();
      if (dupAr.trim()) params.append('NameAr', dupAr.trim());
      if (dupEn.trim()) params.append('NameEn', dupEn.trim());
      if (dupExcludeId.trim()) params.append('TradeNameId', dupExcludeId.trim());

      const resp = await fetch(`${API_BASE}/TradeName/IsTradeNameExist?${params.toString()}`, {
        headers: {
          'X-Channel': channel,
        },
      });
      if (!resp.ok) {
        throw new Error(`Check failed: ${resp.status}`);
      }
      const data = await resp.json();
      setDupResult(data);
    } catch (err) {
      alert(`Duplicate check error: ${err.message}`);
    } finally {
      setDupLoading(false);
    }
  };

  return (
    <div className="tab-pane active" id="tab-search">
      <div className="grid-2col">
        {/* Left Column: Search & Duplicate Inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Hybrid Keyword Search Card */}
          <div className="card">
            <div className="card-header">
              <h2 className="card-title">
                <span>🔍</span>
                <span>{isAr ? 'البحث الذكي في السجل التجاري' : 'Smart Registry Search'}</span>
              </h2>
              <span className="badge badge-info">F19 • F22</span>
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '16px' }}>
              {isAr
                ? 'بحث هجين متعدد الأنماط (متجه، صوتي، وتطابق ثلاثي) عبر قاعدة الأسماء التجارية النشطة في أم القيوين.'
                : 'Hybrid multi-index search (vector, phonetic, trigram) across active UAQ registered trade names.'}
            </p>

            <form onSubmit={handleKeywordSearch}>
              <div className="form-group">
                <label className="form-label">{isAr ? 'كلمة البحث (عربي أو إنجليزي):' : 'Search Keyword (Arabic or English):'}</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder={isAr ? 'مثال: النور، Al Noor، الصقر...' : 'e.g. Al Noor, Falcon, الصقر...'}
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                />
              </div>

              <div className="form-row" style={{ alignItems: 'flex-end', marginTop: '12px' }}>
                <div className="form-group" style={{ flex: '1' }}>
                  <label className="form-label">{isAr ? 'أقصى عدد للنتائج:' : 'Max Results:'}</label>
                  <select
                    className="form-input"
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                  >
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                  </select>
                </div>
                <div style={{ flex: '2' }}>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ width: '100%' }}
                    disabled={searchLoading || !keyword.trim()}
                  >
                    {searchLoading ? (isAr ? 'جاري البحث...' : 'Searching...') : (isAr ? '🔍 بدء البحث' : '🔍 Execute Search')}
                  </button>
                </div>
              </div>
            </form>
          </div>

          {/* Fast Duplicate Check Card */}
          <div className="card">
            <div className="card-header">
              <h2 className="card-title">
                <span>⚡</span>
                <span>{isAr ? 'فحص التطابق الدقيق (IsTradeNameExist)' : 'Fast Duplicate Check (IsTradeNameExist)'}</span>
              </h2>
              <span className="badge badge-info">F2 Spec §5.2</span>
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '16px' }}>
              {isAr
                ? 'فحص فوري عالي السرعة للتحقق من عدم تكرار الاسم في السجل التجاري القائم مع استثناء السجل الحالي أثناء التعديل.'
                : 'Sub-millisecond exact duplicate check against active names, excluding the record being edited.'}
            </p>

            <form onSubmit={handleDuplicateCheck}>
              <div className="form-group">
                <label className="form-label">{isAr ? 'الاسم التجاري بالعربية:' : 'Arabic Trade Name:'}</label>
                <input
                  type="text"
                  className="form-input rtl"
                  placeholder="شركة النور للتجارة"
                  value={dupAr}
                  onChange={(e) => setDupAr(e.target.value)}
                />
              </div>

              <div className="form-group" style={{ marginTop: '12px' }}>
                <label className="form-label">{isAr ? 'الاسم التجاري بالإنجليزية:' : 'English Trade Name:'}</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Al Noor Trading Co"
                  value={dupEn}
                  onChange={(e) => setDupEn(e.target.value)}
                />
              </div>

              <div className="form-row" style={{ alignItems: 'flex-end', marginTop: '12px' }}>
                <div className="form-group" style={{ flex: '1' }}>
                  <label className="form-label">{isAr ? 'معرف مستثنى (اختياري):' : 'Exclude ID (Optional):'}</label>
                  <input
                    type="number"
                    className="form-input"
                    placeholder="e.g. 102"
                    value={dupExcludeId}
                    onChange={(e) => setDupExcludeId(e.target.value)}
                  />
                </div>
                <div style={{ flex: '1.5' }}>
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    style={{ width: '100%' }}
                    disabled={dupLoading || (!dupAr.trim() && !dupEn.trim())}
                  >
                    {dupLoading ? (isAr ? 'جاري الفحص...' : 'Checking...') : (isAr ? '⚡ فحص التكرار' : '⚡ Check Duplicate')}
                  </button>
                </div>
              </div>
            </form>

            {/* Duplicate Check Result Card */}
            {dupResult && (
              <div
                style={{
                  marginTop: '16px',
                  padding: '14px',
                  borderRadius: 'var(--radius)',
                  border: `1px solid ${dupResult.Exists ? 'rgba(244, 63, 94, 0.4)' : 'rgba(52, 211, 153, 0.4)'}`,
                  background: dupResult.Exists ? 'rgba(244, 63, 94, 0.1)' : 'rgba(52, 211, 153, 0.1)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '1.4rem' }}>{dupResult.Exists ? '🚫' : '✅'}</span>
                  <div>
                    <h4 style={{ margin: 0, color: dupResult.Exists ? '#fb7185' : '#34d399' }}>
                      {dupResult.Exists
                        ? (isAr ? 'الاسم التجاري مسجل بالفعل في النظام!' : 'Trade Name Already Exists!')
                        : (isAr ? 'الاسم التجاري متاح وغير مكرر' : 'Trade Name is Available & Not Duplicated')}
                    </h4>
                    {dupResult.Exists && (
                      <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        {isAr ? 'الاسم المطابق المسجل:' : 'Matched Active Name:'}{' '}
                        <strong>{dupResult.MatchedNameAr || dupResult.MatchedNameEn}</strong>
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Search Results Display */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ height: '100%' }}>
            <div className="card-header">
              <h2 className="card-title">
                <span>📋</span>
                <span>{isAr ? 'نتائج مطابقة السجل التجاري' : 'Registry Matching Results'}</span>
              </h2>
              {searchResults && (
                <span className="badge badge-gold">
                  {searchResults.Total} {isAr ? 'سجلات مطابقة' : 'Matches'}
                </span>
              )}
            </div>

            {!searchResults && !searchLoading && (
              <div className="empty-state">
                <span className="empty-icon">🔎</span>
                <p>
                  {isAr
                    ? 'أدخل كلمة البحث في النموذج المقابل لعرض الأسماء المطابقة مع نسب التشابه.'
                    : 'Enter a search keyword on the left to inspect registered trade names and similarity metrics.'}
                </p>
              </div>
            )}

            {searchLoading && (
              <div className="empty-state">
                <span className="empty-icon">⏳</span>
                <p>{isAr ? 'جاري استرجاع السجلات عبر الفهرس الهجين...' : 'Querying hybrid vector & phonetic indexes...'}</p>
              </div>
            )}

            {searchResults && searchResults.Results?.length === 0 && (
              <div className="empty-state">
                <span className="empty-icon">✨</span>
                <p>{isAr ? 'لم يتم العثور على أي أسماء مطابقة في السجل النشط.' : 'No matching active trade names found.'}</p>
              </div>
            )}

            {searchResults && searchResults.Results?.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {searchResults.Results.map((item, idx) => {
                  const scorePct = Math.round((item.similarity_score || 0) * 100);
                  const isHighSim = item.similarity_score >= 0.75;
                  return (
                    <div
                      key={item.registry_id || idx}
                      style={{
                        padding: '14px',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                          <span className="badge badge-info">ID #{item.registry_id}</span>
                          <span
                            className={`badge ${isHighSim ? 'badge-danger' : 'badge-warning'}`}
                          >
                            {isAr ? `تشابه ${scorePct}%` : `${scorePct}% Similarity`}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                          Score: {item.similarity_score}
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ fontSize: '1.05rem', fontWeight: 600 }} className="rtl">
                          {item.normalized_ar || '—'}
                        </div>
                        <div style={{ fontSize: '0.95rem', color: 'var(--text-muted)' }}>
                          {item.normalized_en || '—'}
                        </div>
                      </div>

                      {/* Score Bar */}
                      <div
                        style={{
                          height: '4px',
                          background: 'rgba(255,255,255,0.1)',
                          borderRadius: '2px',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            height: '100%',
                            width: `${Math.min(100, scorePct)}%`,
                            background: isHighSim ? '#f43f5e' : '#f59e0b',
                            borderRadius: '2px',
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
