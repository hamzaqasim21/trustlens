"""
Public Instagram accounts to collect for analysis, grouped by type.

The groups are only a rough guide to what an account is (they are NOT verified
labels). Usernames that do not exist are simply recorded as failed and skipped.
"""

ACCOUNTS = {
    # Pakistani actors, creators, influencers
    "pk_creator": """
        haniaheheofficial mahirahkhan iqrakanwal sajalaly yumnazaidi mawrahocane hadiqakiani
        ayezakhan_official kubrakhan_ minalkhan.official areeka_haq duckybhai shahveerjafry
        irfanjunejo jannatmirza_ sonyahussyn official_mayaali instafood_blog shamidreees
        kanwalaftab rajabbutt94 alizehshahofficial imshaofficial zaidalit_ mathirammohammad
        saboor_aly sarahkhan.official ushnashah_official urwatistic fahadmustafaofficial
        ahadrazamir humayunsaeedofficial fawadkhan81 wahajali_official feroze_khan
        sheheryar_munawar danishtaimoor imranabbas1 aaminaofficial yasirhussain sanajavedofficial
        mehwishhayatofficial ayeza_khan_ aimanxkhan minalkhanofficial mikaalzulfiqar
        humaimamalick sanamjungofficial hira_mani momalsheikh_official nimra_khan_official
        ramshakhan ducky_bhai_official mooroo_official zainabbhatti_ syedabuzar_official
        waqarzaka sheikhsaad_ ahmedaliakbar_ fatima_effendi maazdhillon junaid_akram
        mubashirsaddique_ ghazalaa_official humakhan_ nadiakhanofficial mohsin_abbas_haider
        shaniaghazi anumdawood bilalabbaskhan_official farhansaeedofficial aliaboutit
    """.split(),
    # Global celebrities, athletes, artists
    "global_celeb": """
        cristiano leomessi selenagomez kyliejenner arianagrande therock kimkardashian
        beyonce justinbieber taylorswift neymarjr kevinhart4real virat.kohli championsleague
        khaby00 mrbeast zendaya billieeilish badgalriri dualipa shakira lewishamilton
        k.mbappe vinijr mohamedsalah stephencurry30 jlo emmawatson chrishemsworth
        tomholland2013 priyankachopra deepikapadukone aliaabhatt shraddhakapoor katrinakaif
        iamsrk beingsalmankhan hrithikroshan ranveersingh imVkohli sachintendulkar
        babarazam258 shaheenafridiofficial shoaibmalik.official iamrizwan_rizwan fakharzaman
        naseemshah_official hasanali_official iamimadwasim shadabkhan_official
    """.split(),
    # Brands and companies
    "brand": """
        nike adidas apple samsung cocacola pepsi mcdonalds starbucks netflix spotify
        redbull gucci chanel louisvuitton zara hm ikea airbnb uber tesla bmw mercedesbenz
        google microsoft amazon nasa natgeo bbcnews cnn nytimes dawn_com geonews
        khaadi_pk sanasafinazofficial alkaramstudio gulahmedshop breezeofficial
        nishatlinen sapphirepakistan daraz.pk foodpanda_pk careem jazzpk telenor_pakistan
        zongpakistan kfcpakistan mcdonalds_pakistan dominospakistan hyderabadibiryani
    """.split(),
    # News, media, information pages
    "news_media": """
        bbcworld aljazeeraenglish reuters theeconomist washingtonpost time forbes
        thehindu ndtv arynewsofficial samaatv expresstribune dawn_images thenews_pk
        humnewspk hum.tv ary.digital geoentertainment
    """.split(),
    # Fitness, health, wellness, nutrition (where health claims appear)
    "health_wellness": """
        drmarkhyman drhyman jillianmichaels kayla_itsines chloeting thebodycoach
        joewicks drmikeisraetel drrangan drgundry thefitnesschef_ simnettnutrition
        goop thewellnessmama holistichealth dr.eric.berg dr.rhonda.patrick
        thedietitian eatingwell healthline medicalnewstoday mindbodygreen
        fitnessblender yoga_girl lornajane dailyburn ptsonline drdavidlovin
        dr.sebi_officially herbalremedies_ naturalcures dr.axe jordanyeoh_
    """.split(),
    # Finance, business, crypto, "make money" style accounts (scam-adjacent topics)
    "finance_hustle": """
        garyvee ramit alexhormozi codieSanchez humphreytalks grantcardone
        robbinsresearch tonyrobbins jordanbelfort investopedia financialtimes
        wsj bloomberg cnbc forexsignals_ cryptotrading_ binance coinbase
        tradingview thetraderguy wealthbuilders_ passiveincomeguide_ moneytips101
        sidehustlenation sidehustlepro successdaily businessinsider entrepreneur
        goalcast inspirebusiness_ millionairementor richmindset_ makemoneyonline_
    """.split(),
    # Tech, education, science, government, non-profit
    "tech_edu_org": """
        mit stanford harvard oxford_uni cambridge_uni who unicef unesco redcross
        greenpeace worldwildlife natgeotravel nasahubble spacex elonmusk openai
        github stackoverflow edhi_foundation_official shaukatkhanum_hospital
        lumsofficial nustofficial iba_karachi giki_institute airuniversity
        comsats.official fast_nuces_official
    """.split(),
    # Meme / entertainment / food / travel / lifestyle pages
    "pages_lifestyle": """
        9gag memezar fuckjerry sarcasm ladbible barstoolsports foodies pakistanifoodie
        karachifoodie lahorefoodie islamabadfoodie foodiesofpakistan pakistan.travel
        visitpakistan discoverpakistan travelpakistan northpakistan humansofnewyork
        beautifuldestinations earthpix natgeoyourshot wanderlust pakistaniwedding
        pakistanbridal weddingsbypakistan makeupbypakistan hairbypakistan
    """.split(),
}
