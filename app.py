import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import date, datetime
from math import exp, factorial

st.set_page_config(page_title="Graffias Football Analytics",page_icon="⚽",layout="wide")
st.title("⚽ Graffias Football Analytics")
st.caption("V2 • Canlı futbol verileri • Poisson 1-X-2 • Oran karşılaştırması")
st.warning("İstatistiksel analiz aracıdır. Kazanç garantisi yoktur; otomatik bahis yapmaz.")
try:
    key=st.secrets.get("API_FOOTBALL_KEY","")
except Exception:
    key=""
if not key:
    key=st.text_input("API-Football anahtarınız",type="password")
@st.cache_data(ttl=120,show_spinner=False)
def api(endpoint,params,key):
    r=requests.get("https://v3.football.api-sports.io/"+endpoint,headers={"x-apisports-key":key},params=params,timeout=25)
    r.raise_for_status()
    data=r.json()
    if data.get("errors"):
        raise ValueError(str(data["errors"]))
    return data.get("response",[])
def probabilities(lh,la):
    h=np.array([exp(-lh)*lh**i/factorial(i) for i in range(11)])
    a=np.array([exp(-la)*la**i/factorial(i) for i in range(11)])
    m=np.outer(h,a)
    p=np.array([np.tril(m,-1).sum(),np.trace(m),np.triu(m,1).sum()])
    return p/p.sum()
def analyze(history,fixture):
    kickoff=fixture["fixture"]["date"]
    home=fixture["teams"]["home"]["id"];away=fixture["teams"]["away"]["id"]
    past=[x for x in history if x["fixture"]["date"]<kickoff and x["goals"]["home"] is not None and x["goals"]["away"] is not None]
    if len(past)<12:
        raise ValueError("Bu ligde analiz için en az 12 tamamlanmış maç gerekli.")
    hg=np.mean([x["goals"]["home"] for x in past]);ag=np.mean([x["goals"]["away"] for x in past])
    h=[x for x in past if x["teams"]["home"]["id"]==home][-8:]
    a=[x for x in past if x["teams"]["away"]["id"]==away][-8:]
    if len(h)<3 or len(a)<3:
        raise ValueError("Takımların iç saha/deplasman geçmişi yetersiz.")
    h_for=np.mean([x["goals"]["home"] for x in h]);h_against=np.mean([x["goals"]["away"] for x in h])
    a_for=np.mean([x["goals"]["away"] for x in a]);a_against=np.mean([x["goals"]["home"] for x in a])
    lh=np.clip(hg*(h_for/max(hg,.2))*(a_against/max(hg,.2)),.15,4)
    la=np.clip(ag*(a_for/max(ag,.2))*(h_against/max(ag,.2)),.15,4)
    return float(lh),float(la),probabilities(lh,la),len(past)
tab1,tab2=st.tabs(["🌍 Canlı maçlar ve tahmin","📊 Geçmiş performans testi"])
with tab1:
    day=st.date_input("Tarih",date.today())
    live=st.checkbox("Yalnızca canlı maçlar")
    if st.button("🔄 Maçları getir",type="primary"):
        if not key:st.error("API anahtarı gerekli.")
        else:
            try:
                st.session_state.fixtures=api("fixtures",{"live":"all"} if live else {"date":str(day)},key)
                st.success(f"{len(st.session_state.fixtures)} maç bulundu.")
            except Exception as e:st.error(str(e))
    fixtures=st.session_state.get("fixtures",[])
    if fixtures:
        leagues=sorted(set(x["league"]["name"] for x in fixtures))
        league=st.selectbox("Lig",["Tümü"]+leagues)
        filtered=[x for x in fixtures if league=="Tümü" or x["league"]["name"]==league]
        st.dataframe(pd.DataFrame([{"Lig":x["league"]["name"],"Ev":x["teams"]["home"]["name"],"Deplasman":x["teams"]["away"]["name"],"Skor":str(x["goals"]["home"])+" - "+str(x["goals"]["away"]),"Durum":x["fixture"]["status"]["short"]} for x in filtered]),hide_index=True,use_container_width=True)
        options={str(i+1)+". "+x["teams"]["home"]["name"]+" - "+x["teams"]["away"]["name"]:x for i,x in enumerate(filtered)}
        chosen=st.selectbox("Analiz edilecek maç",list(options))
        if st.button("🎯 Poisson tahmini hesapla"):
            x=options[chosen]
            try:
                history=api("fixtures",{"league":x["league"]["id"],"season":x["league"]["season"],"status":"FT"},key)
                lh,la,p,n=analyze(history,x)
                st.session_state.pred={"p":p.tolist(),"lh":lh,"la":la,"n":n,"fixture":x["fixture"]["id"]}
            except Exception as e:st.error(str(e))
        pred=st.session_state.get("pred")
        if pred:
            st.subheader("1-X-2 olasılıkları")
            cols=st.columns(3)
            for c,label,value in zip(cols,["1 Ev","X Beraberlik","2 Deplasman"],pred["p"]):
                c.metric(label,f"{value*100:.1f}%")
            st.caption(f"Gol bazlı beklenti: {pred['lh']:.2f} / {pred['la']:.2f}; örneklem: {pred['n']} maç. Gerçek xG değildir.")
            if st.button("💹 Oranları karşılaştır"):
                try:
                    offers=api("odds",{"fixture":pred["fixture"]},key)
                    rows=[]
                    for item in offers:
                        for bookmaker in item.get("bookmakers",[]):
                            for bet in bookmaker.get("bets",[]):
                                if bet.get("id")!=1:continue
                                for v in bet.get("values",[]):
                                    idx={"Home":0,"Draw":1,"Away":2}.get(v["value"])
                                    if idx is None:continue
                                    odd=float(v["odd"]);prob=pred["p"][idx]
                                    rows.append({"Şirket":bookmaker["name"],"Sonuç":["1","X","2"][idx],"Oran":odd,"Model %":round(prob*100,1),"Teorik EV %":round((prob*odd-1)*100,1)})
                    if rows:st.dataframe(pd.DataFrame(rows).sort_values("Teorik EV %",ascending=False),hide_index=True)
                    else:st.info("Erişilebilir oran bulunamadı. API planı oran verilerini kapsamayabilir.")
                except Exception as e:st.error(str(e))
            st.caption("Canlı skorlar, maç öncesi Poisson modelini otomatik olarak güncellemez. Resmî İddaa oranları farklı olabilir.")
with tab2:
    st.write("Geçmiş sonuçlarla değerlendirme için CSV yükleyin: date,home,away,hg,ag,odd_h,odd_d,odd_a")
    upload=st.file_uploader("Geçmiş maç CSV",type="csv")
    if upload:
        try:
            df=pd.read_csv(upload).sort_values("date").reset_index(drop=True)
            needed={"date","home","away","hg","ag","odd_h","odd_d","odd_a"}
            if not needed.issubset(df.columns):raise ValueError("Eksik sütunlar: "+str(needed-set(df.columns)))
            results=[]
            for i in range(30,len(df)):
                past=df.iloc[:i];row=df.iloc[i]
                hg=max(.2,past.hg.mean());ag=max(.2,past.ag.mean())
                home=past[past.home==row.home].tail(8);away=past[past.away==row.away].tail(8)
                if len(home)<3 or len(away)<3:continue
                lh=float(np.clip(hg*(home.hg.mean()/hg)*(away.hg.mean()/hg),.15,4))
                la=float(np.clip(ag*(away.ag.mean()/ag)*(home.ag.mean()/ag),.15,4))
                p=probabilities(lh,la);actual=0 if row.hg>row.ag else 1 if row.hg==row.ag else 2
                odds=[row.odd_h,row.odd_d,row.odd_a]
                idx=int(np.argmax(p*np.array(odds)-1))
                ev=p[idx]*odds[idx]-1
                pnl=odds[idx]-1 if idx==actual else -1
                results.append({"Doğru":int(np.argmax(p)==actual),"Brier":sum((p-np.eye(3)[actual])**2),"EV":ev,"Getiri":pnl if ev>.05 else 0,"Seçim":ev>.05})
            if not results:st.warning("Yeterli takım geçmişi bulunamadı.")
            else:
                res=pd.DataFrame(results);c1,c2,c3=st.columns(3)
                c1.metric("Test maçı",len(res));c2.metric("1-X-2 doğruluk",f"{res.Doğru.mean()*100:.1f}%");c3.metric("Brier skoru",f"{res.Brier.mean():.3f}")
                selected=res[res["Seçim"]]
                st.write(f"EV > %5 varsayımıyla {len(selected)} teorik seçim; toplam birim sonuç: {selected.Getiri.sum():.2f}. Geçmiş sonuç gelecek getiriyi garanti etmez.")
        except Exception as e:st.error(str(e))
