function speak(text) {
  if (!text) return;

  if (!('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) {
    alert('이 브라우저는 음성 재생을 지원하지 않습니다.\n(사파리/크롬 앱으로 열어보세요)');
    return;
  }

  const synth = window.speechSynthesis;

  // iOS에서는 백그라운드 이후 재생이 paused 상태로 멈춰있는 경우가 있어 재개시킴
  if (synth.paused) synth.resume();
  synth.cancel();

  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = 'en-US';
  utter.rate = 0.95;
  utter.volume = 1;

  const voices = synth.getVoices();
  const enVoice = voices.find(v => v.lang && v.lang.toLowerCase().startsWith('en'));
  if (enVoice) utter.voice = enVoice;

  utter.onerror = (e) => {
    console.error('speech synthesis error', e);
    alert('음성 재생에 실패했습니다. 기기의 무음 모드/음량을 확인해주세요.');
  };

  synth.speak(utter);
}

function toggleAllWords(source) {
  document.querySelectorAll('input[name="word_ids"]').forEach(cb => cb.checked = source.checked);
}

async function autoFillMeaning(wordInputId, meaningInputId, exampleInputId, btnId) {
  const word = document.getElementById(wordInputId).value.trim();
  if (!word) {
    alert('영단어를 먼저 입력하세요.');
    return;
  }

  const btn = document.getElementById(btnId);
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '조회 중...';

  try {
    const res = await fetch(`/api/lookup?word=${encodeURIComponent(word)}`);
    const data = await res.json();
    if (data.meaning) document.getElementById(meaningInputId).value = data.meaning;
    if (data.example) document.getElementById(exampleInputId).value = data.example;
  } catch (e) {
    alert('자동 조회 중 오류가 발생했습니다.');
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}
