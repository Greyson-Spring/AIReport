export const RES_BASE_URL = "/static/res/logo/"
export const Avatar = (url) => {
  // if (url.startsWith('http://') || url.startsWith('https://')) {
  //     return `${RES_BASE_URL}${url}`;
  //   }
    return url;
}
export const ProxyImage=(content) =>{
  if (!content || typeof content !== 'string') return content;
  // 把微信图片地址改走后端代理(/static/res/logo/...), 解决防盗链"此图片来自微信公众平台未经允许不可引用"
  return content.replace(
    /(<img[^>]*?src=["'])(https?:\/\/(?:mmbiz\.qpic\.cn|mmbiz\.qlogo\.cn|mmecoa\.qpic\.cn)\/[^"']*)/g,
    '$1/static/res/logo/$2'
  );
}